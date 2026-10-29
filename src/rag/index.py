import hashlib
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from database.shop_db.sku_sync_service import REPO_ROOT, load_manifest, validate_manifest

from .chunker import CHUNK_CONFIG, Chunk, chunk_document

ACCESS_LEVELS = ("public", "staff", "admin")
INDEX_ROOT = REPO_ROOT / "artifacts" / "index"
# One active pointer per embedding provider, so the offline (fake) index and the Gemini index can both stay
# usable: the Gemini one is the main runtime index, the fake one serves tests, CI and machines without a key.
POINTER_PATHS = {"gemini": REPO_ROOT / "artifacts" / "index_manifest.json",
                 "fake": REPO_ROOT / "artifacts" / "index_manifest_fake.json"}


class IndexIntegrityError(Exception):
    pass


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _npy_bytes(matrix) -> bytes:
    buffer = io.BytesIO()
    np.save(buffer, matrix.astype(np.float32), allow_pickle=False)
    return buffer.getvalue()


def _relative(path) -> str:
    path = Path(path).resolve()
    return path.relative_to(REPO_ROOT).as_posix() if path.is_relative_to(REPO_ROOT) else str(path)


def build_bundle(manifest_path, embedder, out_root=INDEX_ROOT, repo_root=REPO_ROOT):
    """Validate the corpus manifest, chunk every document and write one vector file per access level."""
    manifest_path = Path(manifest_path)
    manifest = load_manifest(manifest_path)
    report = validate_manifest(manifest, repo_root)
    if not report["ok"]:
        raise IndexIntegrityError("Manifest không hợp lệ: " + "; ".join(e["detail"] for e in report["errors"][:5]))
    chunks = [c for entry in manifest["documents"] for c in chunk_document(entry, repo_root)]
    if len({c.chunk_id for c in chunks}) != len(chunks):
        raise IndexIntegrityError("chunk_id bị trùng")
    bundle = Path(out_root) / f"{manifest['corpus_release']}-{embedder.provider}"
    bundle.mkdir(parents=True, exist_ok=True)
    files, rows = {}, []
    for level in ACCESS_LEVELS:
        level_chunks = [c for c in chunks if c.access_level == level]
        data = _npy_bytes(embedder.embed_documents(level_chunks))
        (bundle / f"vectors_{level}.npy").write_bytes(data)
        files[f"vectors_{level}.npy"] = _sha256(data)
        rows += [{**c.to_dict(), "row": i} for i, c in enumerate(level_chunks)]
    chunk_bytes = "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows).encode()
    (bundle / "chunks.jsonl").write_bytes(chunk_bytes)
    files["chunks.jsonl"] = _sha256(chunk_bytes)
    index_manifest = {
        "index_id": f"{manifest['corpus_release']}-{embedder.provider}-{files['chunks.jsonl'][:8]}",
        "corpus_release": manifest["corpus_release"],
        "manifest_path": _relative(manifest_path),
        "manifest_sha256": _sha256(manifest_path.read_bytes()),
        "embedding": {"provider": embedder.provider, "model": embedder.model, "revision": embedder.revision,
                      "dimension": embedder.dimension, "query_encoding": embedder.query_encoding,
                      "document_encoding": embedder.document_encoding, "normalization": "l2",
                      "metric": "cosine (dot product of L2-normalised vectors)"},
        "chunk_config": CHUNK_CONFIG,
        "chunk_count": len(chunks),
        "chunks_by_access": {level: sum(c.access_level == level for c in chunks) for level in ACCESS_LEVELS},
        "documents": [{"doc_id": e["doc_id"], "version": e["version"], "source": e["source_path"],
                       "access_level": e["access_level"], "content_sha256": e["content_sha256"]}
                      for e in manifest["documents"]],
        "files": files,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    (bundle / "index_manifest.json").write_text(json.dumps(index_manifest, ensure_ascii=False, indent=2) + "\n",
                                                encoding="utf-8")
    return bundle, index_manifest


class IndexBundle:
    """A loaded bundle whose files were checked against its manifest before any query can use them."""

    def __init__(self, bundle_dir):
        self.dir = Path(bundle_dir)
        try:
            self.manifest = json.loads((self.dir / "index_manifest.json").read_text(encoding="utf-8"))
            for name, expected in self.manifest["files"].items():
                if _sha256((self.dir / name).read_bytes()) != expected:
                    raise IndexIntegrityError(f"{name} không khớp sha256 trong index_manifest")
            rows = [json.loads(line) for line in (self.dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines()]
            self.vectors = {level: np.load(self.dir / f"vectors_{level}.npy", allow_pickle=False)
                            for level in ACCESS_LEVELS}
        except (OSError, ValueError, KeyError) as err:
            raise IndexIntegrityError(f"Không đọc được index bundle: {type(err).__name__}") from None
        self.chunks = {level: [] for level in ACCESS_LEVELS}
        for row in sorted(rows, key=lambda r: (r["access_level"], r["row"])):
            row = dict(row)
            row.pop("row")
            self.chunks[row["access_level"]].append(Chunk(**row))
        dimension = self.manifest["embedding"]["dimension"]
        for level in ACCESS_LEVELS:
            matrix = self.vectors[level]
            if len(self.chunks[level]) != matrix.shape[0] or (matrix.size and matrix.shape[1] != dimension):
                raise IndexIntegrityError(f"Mapping chunk/vector của mức {level} không khớp")
        if sum(len(v) for v in self.chunks.values()) != self.manifest["chunk_count"]:
            raise IndexIntegrityError("Số chunk không khớp index_manifest")

    @property
    def index_id(self):
        return self.manifest["index_id"]

    @property
    def corpus_release(self):
        return self.manifest["corpus_release"]

    def chunk(self, chunk_id, levels):
        return next((c for level in levels for c in self.chunks[level] if c.chunk_id == chunk_id), None)


def activate(bundle_dir, pointer_path):
    """Atomically point the runtime at a bundle (validated first, so a broken bundle never becomes active)."""
    bundle = IndexBundle(bundle_dir)
    pointer = {**bundle.manifest, "bundle_dir": _relative(bundle.dir),
               "activated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    pointer_path = Path(pointer_path)
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pointer_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pointer, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, pointer_path)
    return bundle


def load_active(pointer_path):
    try:
        pointer = json.loads(Path(pointer_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise IndexIntegrityError("Chưa có index active (artifacts/index_manifest.json)") from None
    bundle_dir = Path(pointer["bundle_dir"])
    bundle = IndexBundle(bundle_dir if bundle_dir.is_absolute() else REPO_ROOT / bundle_dir)
    if bundle.manifest["files"] != pointer.get("files"):
        raise IndexIntegrityError("Con trỏ index active không khớp bundle trên đĩa")
    return bundle
