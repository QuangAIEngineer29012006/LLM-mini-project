"""Serve the Gemini index built by gemini_index.py through the same interface as IndexBundle."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from database.shop_db.sku_sync_service import REPO_ROOT, load_manifest

from . import gemini_index
from .chunker import Chunk
from .index import ACCESS_LEVELS, IndexIntegrityError, _relative
from .retriever import Hit

# Cosine cut-off for context, chosen on the dev split for gemini-embedding-001 (3072 dims):
# answerable top-1 >= 0.768, no-evidence top-1 <= 0.671.
MIN_SCORE = 0.72


def describe(raw):
    """Map gemini_index's manifest onto the field names the service, admin API and UI already use."""
    counts = raw.get("access_level_chunk_counts", {})
    return {"index_id": f"{raw['corpus_release']}-gemini-{raw['index_sha256'][:8]}",
            "corpus_release": raw["corpus_release"], "manifest_path": raw["corpus_manifest_path"],
            "embedding": {"provider": "gemini", "model": raw["embedding_model"],
                          "dimension": raw["embedding_dimensions"], "query_encoding": raw["query_encoding"],
                          "document_encoding": raw["document_encoding"], "metric": raw["metric"]},
            "chunk_config": {"strategy": raw["chunk_strategy"], "max_chars": raw["chunk_max_chars"],
                             "overlap_chars": raw["chunk_overlap_chars"]},
            "chunk_count": raw["chunk_count"],
            "chunks_by_access": {level: counts.get(level, 0) for level in ACCESS_LEVELS},
            "index_sha256": raw["index_sha256"], "built_at": raw["created_at_utc"]}


def summary(index_dir):
    path = Path(index_dir) / gemini_index.INDEX_MANIFEST_NAME
    return describe(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else None


class GeminiIndex:
    """A release's Gemini index, validated once on load (hashes, mapping, vectors) instead of on every query."""

    def __init__(self, index_dir, manifest_path):
        self.dir = Path(index_dir)
        try:
            raw, self.rows = gemini_index.validate_index(manifest_path, self.dir)
        except gemini_index.RAGError as err:
            raise IndexIntegrityError(str(err)) from None
        self.manifest = describe(raw)
        entries = {e["doc_id"]: e for e in load_manifest(Path(manifest_path))["documents"]}
        self.chunks = {level: [] for level in ACCESS_LEVELS}
        self.by_id = {}
        for row in self.rows:
            entry = entries[row["doc_id"]]
            # gemini_index re-joins words when it splits long sections, so chunks carry no source offsets (-1).
            chunk = Chunk(chunk_id=row["chunk_id"], doc_id=row["doc_id"], title=row["title"], section=row["section"],
                          source=row["source"], version=row["version"], access_level=row["access_level"],
                          doc_type=entry["doc_type"], char_start=-1, char_end=-1, skus=list(entry.get("skus", [])),
                          product_ids=list(entry.get("product_ids", [])), text=row["text"], sha256="")
            self.chunks[chunk.access_level].append(chunk)
            self.by_id[chunk.chunk_id] = chunk

    @property
    def index_id(self):
        return self.manifest["index_id"]

    @property
    def corpus_release(self):
        return self.manifest["corpus_release"]

    def chunk(self, chunk_id, levels):
        chunk = self.by_id.get(chunk_id)
        return chunk if chunk and chunk.access_level in levels else None

    def retrieve(self, query, role, k=5):
        """Rank with gemini_index.retrieve (role filter before similarity) and wrap results for the service."""
        hits = gemini_index.retrieve(query, role=role, top_k=k, chunks=self.rows)
        return [Hit(self.by_id[h["chunk_id"]], h["score"], h["rank"]) for h in hits]


def build(manifest_path, index_root):
    raw = gemini_index.build_index(manifest_path, Path(index_root) / f"{load_manifest(Path(manifest_path))['corpus_release']}-gemini")
    return describe(raw)


def activate(index_dir, manifest_path, pointer_path):
    """Validate the index, then atomically point the runtime at it."""
    index = GeminiIndex(index_dir, manifest_path)
    pointer = {**index.manifest, "index_dir": _relative(index.dir),
               "activated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    pointer_path = Path(pointer_path)
    tmp = pointer_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, pointer_path)
    return index


def load_active(pointer_path):
    try:
        pointer = json.loads(Path(pointer_path).read_text(encoding="utf-8"))
        index_dir, manifest_path = Path(pointer["index_dir"]), Path(pointer["manifest_path"])
    except (OSError, ValueError, KeyError):
        raise IndexIntegrityError("Chưa có index Gemini active (artifacts/index_manifest.json)") from None
    index = GeminiIndex(index_dir if index_dir.is_absolute() else REPO_ROOT / index_dir,
                        manifest_path if manifest_path.is_absolute() else REPO_ROOT / manifest_path)
    if index.manifest["index_sha256"] != pointer.get("index_sha256"):
        raise IndexIntegrityError("Con trỏ index active không khớp index trên đĩa")
    return index
