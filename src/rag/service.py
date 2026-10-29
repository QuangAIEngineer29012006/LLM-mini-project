import json
import re
import threading
import time
from collections import OrderedDict
from pathlib import Path

from database.shop_db import corpus_service
from database.shop_db.corpus_errors import CorpusAccessDenied, CorpusNotFound
from database.shop_db.sku_sync_service import REPO_ROOT, load_manifest, sync_from_manifest
from database.shop_db.text_utils import normalize
from src.llm_client import LLMError

from .answer import FakeGenerator, GeminiGenerator, document_frequency
from .embedder import make_embedder
from .index import POINTER_PATHS, IndexBundle, IndexIntegrityError, build_bundle, load_active
from .index import activate as activate_bundle
from .retriever import retrieve, select_context

# Topics that only exist in internal documents. Detected from the question itself so the decision never
# needs content the role may not read (D5). Value = the access level that may ask.
RESTRICTED_TOPICS = {
    "staff": ("noi bo", "sop", "han muc ho tro", "ho tro phi", "sla", "quy trinh xu ly khieu nai",
              "van hanh ton kho", "duyet vuot han muc"),
    "admin": ("tien luong", "muc luong", "bang luong", "luong nhan vien", "phu cap", "ca truc", "ca dem", "nhan su", "re index", "reindex", "rollback",
              "release corpus", "quan tri corpus"),
}
UNSAFE = re.compile(r"bo qua.*(chinh sach|huong dan|quy dinh)|ignore.*(polic|instruction)|tiet lo|system prompt|"
                    r"(tao|cap|xin).*ma (giam gia|khuyen mai)|api[ _-]?key")
MESSAGES = {
    "insufficient_evidence": "Mình chưa tìm thấy thông tin này trong tài liệu của cửa hàng nên không thể khẳng định.",
    "access_denied": "Nội dung này thuộc tài liệu nội bộ, tài khoản hiện tại không có quyền truy cập.",
    "handoff": "Yêu cầu này cần nhân viên hỗ trợ xem xét.",
    "error": "Hệ thống tra cứu tài liệu đang gặp sự cố. Vui lòng thử lại sau.",
}
CACHE_SIZE = 256


def required_level(question):
    text = f" {normalize(question)} "
    for level in ("admin", "staff"):
        if any(f" {topic} " in text for topic in RESTRICTED_TOPICS[level]):
            return level
    return "public"


class KnowledgeService:
    """Read-only knowledge route: never writes orders, prices, stock or payments."""

    def __init__(self, settings, llm_client=None):
        self.settings = settings
        self.embedder = make_embedder(settings)
        self.pointer = Path(settings.rag_index_pointer or POINTER_PATHS[self.embedder.provider])
        self.index_root = self.pointer.parent / "index"
        self.llm = GeminiGenerator(llm_client) if hasattr(llm_client, "complete") else None
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        # IDF-weighted sentence selection for the offline generator (False reproduces the evaluation baseline).
        self.weighted_extraction = True
        self.bundle, self.problem = None, None
        self.reload()

    def reload(self):
        with self.lock:
            self.cache.clear()
            try:
                bundle = load_active(self.pointer)
                if bundle.manifest["embedding"]["provider"] != self.embedder.provider:
                    raise IndexIntegrityError("Index active được build bằng embedding khác cấu hình runtime")
                self.bundle, self.problem = bundle, None
            except IndexIntegrityError as err:
                self.bundle, self.problem = None, str(err)

    def check_release(self, conn):
        """Degrade when the index and the DB metadata point at different corpus releases."""
        if self.bundle is None:
            return
        row = conn.execute("SELECT release FROM corpus_releases WHERE is_active = 1").fetchone()
        if row is None or row["release"] != self.bundle.corpus_release:
            self.problem = (f"Index active ({self.bundle.corpus_release}) khác release corpus trong DB "
                            f"({row['release'] if row else 'chưa có'})")
        elif self.problem and self.problem.startswith("Index active ("):
            self.problem = None

    @property
    def manifest_path(self):
        return REPO_ROOT / self.bundle.manifest["manifest_path"] if self.bundle else None

    @property
    def ready(self):
        return self.bundle is not None and self.problem is None

    def status(self):
        manifest = self.bundle.manifest if self.bundle else {}
        return {"ready": self.ready, "problem": self.problem, "index_id": manifest.get("index_id"),
                "corpus_release": manifest.get("corpus_release"), "embedding": manifest.get("embedding"),
                "chunk_count": manifest.get("chunk_count"), "chunks_by_access": manifest.get("chunks_by_access"),
                "built_at": manifest.get("built_at"), "min_score": self.embedder.min_score, "generator": self.llm.name if self.llm else "fake-extractive-v1",
                "cache_entries": len(self.cache)}

    def _result(self, status, answer="", citations=(), missing="", **debug):
        return {"status": status, "answer": answer or MESSAGES.get(status, ""), "citations": list(citations),
                "missing_information": missing, "debug": debug}

    def answer(self, conn, question, role):
        start = time.monotonic()
        question = (question or "").strip()
        levels = corpus_service.allowed_access_levels(role)
        if not normalize(question):
            return self._result("insufficient_evidence", missing="Câu hỏi đang trống.")
        if UNSAFE.search(normalize(question)):
            return self._result("handoff", reason="unsafe_request")
        needed = required_level(question)
        if needed not in levels:
            return self._result("access_denied", missing=f"Cần quyền {needed}.", required_level=needed)
        if not self.ready:
            return self._result("error", missing=self.problem or "Index chưa sẵn sàng.")
        key = (self.bundle.index_id, role, normalize(question))
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                return {**self.cache[key], "debug": {**self.cache[key]["debug"], "cache": "hit"}}
        try:
            hits = retrieve(self.bundle, self.embedder, question, role, k=5)
            context = select_context(hits, question, self.embedder.min_score)
            retrieval = [h.debug() for h in hits]
            if not context:
                result = self._result("insufficient_evidence", missing="Không có đoạn tài liệu đủ liên quan.",
                                      retrieval=retrieval, context=[])
            else:
                readable = [c for level in levels for c in self.bundle.chunks[level]]
                generator = self.llm or FakeGenerator(document_frequency(readable), len(readable),
                                                      weighted=self.weighted_extraction)
                result = self._finish(conn, role, generator.generate(question, context), context, retrieval)
        except LLMError as err:
            return self._result("error", missing=err.code)
        result["debug"].update(index_id=self.bundle.index_id, latency_ms=round((time.monotonic() - start) * 1000, 1))
        with self.lock:
            self.cache[key] = result
            while len(self.cache) > CACHE_SIZE:
                self.cache.popitem(last=False)
        return result

    def _finish(self, conn, role, generated, context, retrieval):
        by_id = {h.chunk.chunk_id: h.chunk for h in context}
        context_ids = list(by_id)
        cited = generated["citation_chunk_ids"]
        if any(cid not in by_id for cid in cited):
            # A citation outside the supplied context cannot be trusted; never pass it to the user.
            return self._result("insufficient_evidence", missing="Câu trả lời trích dẫn nguồn không nằm trong context.",
                                retrieval=retrieval, context=context_ids, rejected_citations=cited)
        if generated["status"] != "answered":
            return self._result(generated["status"], missing=generated["missing_information"],
                                retrieval=retrieval, context=context_ids)
        if not cited:
            return self._result("insufficient_evidence", missing="Câu trả lời không có trích dẫn.",
                                retrieval=retrieval, context=context_ids)
        citations = []
        for cid in cited:
            chunk = by_id[cid]
            try:
                resolved = corpus_service.resolve_citation(conn, chunk.doc_id, chunk.version, role=role)
            except (CorpusAccessDenied, CorpusNotFound):
                resolved = None
            if not resolved or not (resolved["source_exists"] and resolved["sha256_matches"] and resolved["is_active_version"]):
                return self._result("error", missing=f"Không xác minh được nguồn {chunk.doc_id}@{chunk.version}.",
                                    retrieval=retrieval, context=context_ids)
            citations.append({"chunk_id": cid, "doc_id": chunk.doc_id, "source": chunk.source,
                              "version": chunk.version, "title": chunk.title, "section": chunk.section})
        return self._result("answered", generated["answer"], citations, retrieval=retrieval, context=context_ids)

    def releases(self):
        """Corpus releases available on disk, each with its manifest and (if built) its bundle summary."""
        found = {}
        for path in sorted((REPO_ROOT / "data_config").glob("corpus_manifest_v*.json")):
            release = load_manifest(path)["corpus_release"]
            bundle_dir = self.index_root / f"{release}-{self.embedder.provider}"
            manifest = bundle_dir / "index_manifest.json"
            found[release] = {"manifest_path": str(path.relative_to(REPO_ROOT)),
                              "bundle": json.loads(manifest.read_text(encoding="utf-8")) if manifest.is_file() else None}
        return found

    def build(self, release):
        info = self.releases().get(release)
        if info is None:
            raise IndexIntegrityError(f"Không có manifest cho release {release}")
        _, manifest = build_bundle(REPO_ROOT / info["manifest_path"], self.embedder, out_root=self.index_root)
        return manifest

    def activate(self, conn, release, actor_id):
        """Switch DB metadata and the index pointer to one release together; old answers are dropped from cache."""
        info = self.releases().get(release)
        if info is None or info["bundle"] is None:
            raise IndexIntegrityError(f"Release {release} chưa được build index")
        bundle_dir = self.index_root / f"{release}-{self.embedder.provider}"
        IndexBundle(bundle_dir)
        sync_from_manifest(conn, REPO_ROOT / info["manifest_path"], actor_type="admin", actor_id=actor_id)
        activate_bundle(bundle_dir, self.pointer)
        self.reload()
        self.check_release(conn)
        return self.status()

    def source(self, chunk_id, role):
        """Return the cited section text for the citation viewer, only from levels the role may read."""
        if self.bundle is None:
            return None
        return self.bundle.chunk(chunk_id, corpus_service.allowed_access_levels(role))
