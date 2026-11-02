"""Corpus ingestion, chunking, Gemini embeddings, index validation and retrieval."""
import hashlib
import json
import math
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from pathlib import Path

import time

import requests
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

_DEFAULT_CORPUS_MANIFEST = ROOT / "data_config" / "corpus_manifest_v1.1.json"
CORPUS_MANIFEST_FILE = Path(os.getenv("RAG_CORPUS_MANIFEST", str(_DEFAULT_CORPUS_MANIFEST)))
if not CORPUS_MANIFEST_FILE.is_absolute():
    CORPUS_MANIFEST_FILE = ROOT / CORPUS_MANIFEST_FILE
# One index directory per corpus release, so an older release can be re-activated without re-embedding.
INDEX_ROOT = ROOT / "artifacts" / "index"
INDEX_FILE_NAME = "rag_index.json"
INDEX_MANIFEST_NAME = "index_manifest.json"

EMBEDDING_MODEL = os.getenv("RAG_EMBEDDING_MODEL", "gemini-embedding-001")
INDEX_FORMAT_VERSION = "2.0"
MAX_CHUNK_CHARS = 900
CHUNK_OVERLAP_CHARS = 120
ROLE_ACCESS = {
    "customer": {"public"},
    "public": {"public"},
    "staff": {"public", "staff"},
    "admin": {"public", "staff", "admin"},
}
_GENERIC_TERMS = {
    "va", "la", "cua", "hang", "cho", "ve", "trong", "voi", "cac", "nhung",
    "quy", "dinh", "noi", "bo", "tai", "lieu", "huong", "dan", "trinh",
    "thong", "tin", "khach", "nhan", "vien", "duoc", "co", "khong", "bao", "nhieu",
}


class RAGError(RuntimeError):
    """A safe, user-displayable RAG pipeline error."""


def index_dir_for(release):
    return INDEX_ROOT / f"{release}-gemini"


def _read_manifest(manifest_path=None):
    try:
        raw = Path(manifest_path or CORPUS_MANIFEST_FILE).read_bytes()
        if raw.startswith(b"\xef\xbb\xbf"):
            raise RAGError("Corpus manifest has a UTF-8 BOM")
        normalized = raw.replace(b"\r\n", b"\n")
        manifest = json.loads(normalized.decode("utf-8", errors="strict"))
    except RAGError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RAGError("Corpus manifest is missing or invalid JSON/UTF-8") from error

    if not isinstance(manifest, dict) or not isinstance(manifest.get("documents"), list):
        raise RAGError("Corpus manifest must contain a documents list")
    if not isinstance(manifest.get("corpus_release"), str) or not manifest["corpus_release"].strip():
        raise RAGError("Corpus manifest is missing corpus_release")
    return manifest, hashlib.sha256(normalized).hexdigest()


def _safe_document_path(source_path):
    if not isinstance(source_path, str) or not source_path.startswith("data_config/corpus/"):
        raise RAGError("Corpus source_path must point inside data_config/corpus")
    if "\\" in source_path or any(part in {"", ".", ".."} for part in source_path.split("/")):
        raise RAGError("Corpus source_path is not a safe relative path")
    corpus_root = (ROOT / "data_config" / "corpus").resolve()
    resolved = (ROOT / source_path).resolve()
    try:
        resolved.relative_to(corpus_root)
    except ValueError as error:
        raise RAGError("Corpus source_path escapes the corpus folder") from error
    return resolved


def _load_documents(manifest):
    documents = []
    seen_ids = set()
    required = ("doc_id", "title", "source_path", "version", "access_level", "content_sha256", "file_size_bytes")

    for position, item in enumerate(manifest["documents"], start=1):
        if not isinstance(item, dict) or any(not item.get(key) for key in required):
            raise RAGError(f"Corpus document {position} is missing required metadata")
        doc_id = item["doc_id"]
        if doc_id in seen_ids:
            raise RAGError(f"Duplicate corpus doc_id: {doc_id}")
        seen_ids.add(doc_id)
        if item["access_level"] not in {"public", "staff", "admin"}:
            raise RAGError(f"Invalid access level for {doc_id}")

        path = _safe_document_path(item["source_path"])
        try:
            raw = path.read_bytes()
        except OSError as error:
            raise RAGError(f"Corpus source file is missing: {item['source_path']}") from error
        if raw.startswith(b"\xef\xbb\xbf"):
            raise RAGError(f"Corpus source has a UTF-8 BOM: {item['source_path']}")
        normalized = raw.replace(b"\r\n", b"\n")
        try:
            text = normalized.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise RAGError(f"Corpus source is not valid UTF-8: {item['source_path']}") from error
        if not text.strip():
            raise RAGError(f"Corpus source is empty: {item['source_path']}")
        if hashlib.sha256(normalized).hexdigest() != item["content_sha256"]:
            raise RAGError(f"Corpus source hash differs from manifest: {item['source_path']}")
        if len(normalized) != item["file_size_bytes"]:
            raise RAGError(f"Corpus source size differs from manifest: {item['source_path']}")

        front_matter = re.match(r"\A---\s*\n(.*?)\n---\s*\n", text, flags=re.S)
        if not front_matter:
            raise RAGError(f"Corpus file is missing Markdown front matter: {item['source_path']}")
        fm = {}
        for line in front_matter.group(1).splitlines():
            key, sep, value = line.partition(":")
            if sep:
                fm[key.strip()] = value.strip()
        for key in ("doc_id", "title", "version", "access_level"):
            if fm.get(key) != str(item[key]):
                raise RAGError(f"Manifest/front-matter {key} mismatch for {doc_id}")

        documents.append({
            "doc_id": doc_id,
            "title": item["title"],
            "source": item["source_path"],
            "version": item["version"],
            "access_level": item["access_level"],
            "content_sha256": item["content_sha256"],
            "text": text,
        })

    if not documents:
        raise RAGError("Corpus contains no documents")
    return documents


def load_documents(manifest_path=None):
    """Load active manifest documents after validating source paths and hashes."""
    manifest, _ = _read_manifest(manifest_path)
    return _load_documents(manifest)


def _terms(text):
    plain = unicodedata.normalize("NFD", text.lower().replace("đ", "d"))
    plain = "".join(char for char in plain if unicodedata.category(char) != "Mn")
    return {word for word in re.findall(r"[a-z0-9]+", plain) if len(word) > 1}


def is_restricted_topic(question, role="customer", manifest_path=None):
    """Flag likely ACL-denied requests using restricted document titles only.

    Restricted document bodies and vectors are never searched for this check.
    """
    if role not in ROLE_ACCESS:
        raise RAGError("Unknown user role")
    if not question or role == "admin":
        return False

    query_terms = _terms(question) - _GENERIC_TERMS
    manifest, _ = _read_manifest(manifest_path)
    for document in manifest["documents"]:
        if document.get("access_level") in ROLE_ACCESS[role]:
            continue
        title_terms = _terms(document.get("title", "")) - _GENERIC_TERMS
        if len(query_terms & title_terms) >= 2:
            return True
    return False


def split_into_chunks(text):
    """Keep Markdown sections intact; split oversized sections at word boundaries."""
    text = re.sub(r"\A---\s*\n.*?\n---\s*\n", "", text, count=1, flags=re.S)
    sections = re.split(r"(?m)(?=^#{1,6}\s+)", text)
    chunks = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= MAX_CHUNK_CHARS:
            chunks.append(section)
            continue

        lines = section.splitlines()
        heading = lines[0].strip() if lines[0].lstrip().startswith("#") else ""
        body = "\n".join(lines[1:]).strip() if heading else section
        body_limit = max(200, MAX_CHUNK_CHARS - len(heading) - 1)
        current = ""
        for word in body.split():
            proposed = f"{current} {word}".strip()
            if len(proposed) > body_limit and current:
                chunks.append(f"{heading}\n{current}".strip())
                current = f"{current[-CHUNK_OVERLAP_CHARS:]} {word}".strip()
            else:
                current = proposed
        if current:
            chunks.append(f"{heading}\n{current}".strip())
    return chunks


def _expected_chunks(documents):
    expected = []
    for document in documents:
        for number, text in enumerate(split_into_chunks(document["text"]), start=1):
            first_line = text.splitlines()[0].strip() if text else ""
            match = re.match(r"^#{1,6}\s+(.+)$", first_line)
            expected.append({
                "chunk_id": f"{document['doc_id']}:{number}",
                "doc_id": document["doc_id"],
                "title": document["title"],
                "source": document["source"],
                "version": document["version"],
                "access_level": document["access_level"],
                "section": match.group(1) if match else "Introduction",
                "text": text,
            })
    return expected


def embed_text(text, task_type, retries=3):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RAGError("Set GEMINI_API_KEY in your .env file")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:embedContent"
    try:
        for attempt in range(retries + 1):
            response = requests.post(
                url,
                headers={"x-goog-api-key": api_key},
                json={
                    "model": f"models/{EMBEDDING_MODEL}",
                    "content": {"parts": [{"text": text}]},
                    "taskType": task_type,
                },
                timeout=20,
            )
            # The free tier limits embeddings per minute; a full build waits instead of failing halfway.
            if response.status_code != 429 or attempt == retries:
                break
            time.sleep(30)
        response.raise_for_status()
        vector = response.json()["embedding"]["values"]
    except (requests.RequestException, KeyError, TypeError, ValueError) as error:
        raise RAGError("Gemini embedding request failed or returned invalid data") from error
    if not isinstance(vector, list) or not vector or any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in vector
    ):
        raise RAGError("Gemini returned an invalid embedding vector")
    return [float(value) for value in vector]


def _atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _make_index_manifest(corpus_manifest, corpus_hash, manifest_file, chunks, index_bytes):
    dimensions = len(chunks[0]["embedding"]) if chunks else 0
    access_counts = {}
    for chunk in chunks:
        access_counts[chunk["access_level"]] = access_counts.get(chunk["access_level"], 0) + 1
    try:
        manifest_path = manifest_file.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        manifest_path = str(manifest_file.resolve())
    return {
        "index_format_version": INDEX_FORMAT_VERSION,
        "index_version": f"{corpus_manifest['corpus_release']}-rag-{INDEX_FORMAT_VERSION}",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "corpus_release": corpus_manifest["corpus_release"],
        "corpus_manifest_path": manifest_path,
        "corpus_manifest_sha256": corpus_hash,
        "embedding_model": EMBEDDING_MODEL,
        "embedding_dimensions": dimensions,
        "document_encoding": "RETRIEVAL_DOCUMENT",
        "query_encoding": "RETRIEVAL_QUERY",
        "normalization": "Gemini embedding values; cosine similarity computed at retrieval",
        "metric": "cosine_similarity",
        "chunk_strategy": "markdown_section_aware_word_split",
        "chunk_max_chars": MAX_CHUNK_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "document_count": len(corpus_manifest["documents"]),
        "chunk_count": len(chunks),
        "access_level_chunk_counts": access_counts,
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
    }


def _paths(manifest_path, index_dir, corpus_manifest):
    manifest_file = Path(manifest_path or CORPUS_MANIFEST_FILE)
    folder = Path(index_dir) if index_dir else index_dir_for(corpus_manifest["corpus_release"])
    return manifest_file, folder / INDEX_FILE_NAME, folder / INDEX_MANIFEST_NAME


def build_index(manifest_path=None, index_dir=None):
    """Build new vectors and atomically publish the index and its manifest."""
    corpus_manifest, corpus_hash = _read_manifest(manifest_path)
    manifest_file, index_file, index_manifest_file = _paths(manifest_path, index_dir, corpus_manifest)
    documents = _load_documents(corpus_manifest)
    expected = _expected_chunks(documents)
    chunks = []
    dimensions = None

    for item in expected:
        vector = embed_text(item["text"], "RETRIEVAL_DOCUMENT")
        if dimensions is None:
            dimensions = len(vector)
        elif dimensions != len(vector):
            raise RAGError("Embedding dimensions changed during index build")
        chunks.append({**item, "embedding": vector})

    index_bytes = json.dumps(chunks, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    index_manifest = _make_index_manifest(corpus_manifest, corpus_hash, manifest_file, chunks, index_bytes)
    manifest_bytes = json.dumps(index_manifest, ensure_ascii=False, indent=2).encode("utf-8")

    # If interrupted between replacements, validation rejects the mismatched pair.
    _atomic_write(index_file, index_bytes)
    _atomic_write(index_manifest_file, manifest_bytes)
    return index_manifest


def refresh_index_manifest(manifest_path=None, index_dir=None):
    """Adopt a previously built index only if its chunks match today's corpus exactly.

    This updates metadata only and makes no embedding API calls.
    """
    corpus_manifest, corpus_hash = _read_manifest(manifest_path)
    manifest_file, index_file, index_manifest_file = _paths(manifest_path, index_dir, corpus_manifest)
    documents = _load_documents(corpus_manifest)
    expected = _expected_chunks(documents)
    try:
        old_manifest = json.loads(index_manifest_file.read_text(encoding="utf-8"))
        index_bytes = index_file.read_bytes()
        stored_index = json.loads(index_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RAGError("Existing index or index manifest is missing/invalid") from error

    for key, value in {
        "embedding_model": EMBEDDING_MODEL,
        "document_encoding": "RETRIEVAL_DOCUMENT",
        "query_encoding": "RETRIEVAL_QUERY",
        "metric": "cosine similarity",
        "chunk_max_chars": MAX_CHUNK_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "document_count": len(documents),
        "chunk_count": len(expected),
    }.items():
        if old_manifest.get(key) != value:
            raise RAGError(f"Cannot safely refresh manifest: old {key} does not match")
    # Earlier starter builds wrapped chunks in {"chunks": [...]}; normalize that format.
    chunks = stored_index.get("chunks") if isinstance(stored_index, dict) else stored_index
    if not isinstance(chunks, list) or len(chunks) != len(expected):
        raise RAGError("Existing index chunks do not match the current corpus; rebuild required")

    dimensions = None
    section_metadata_added = False
    for actual, wanted in zip(chunks, expected):
        comparable = {key: value for key, value in wanted.items() if key != "section"}
        if any(actual.get(key) != value for key, value in comparable.items()):
            raise RAGError(f"Existing index mapping/text differs at {wanted['chunk_id']}; rebuild required")
        if "section" not in actual:
            actual["section"] = wanted["section"]
            section_metadata_added = True
        elif actual["section"] != wanted["section"]:
            raise RAGError(f"Existing index section mapping differs at {wanted['chunk_id']}; rebuild required")
        vector = actual.get("embedding")
        if not isinstance(vector, list) or not vector or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in vector
        ):
            raise RAGError(f"Invalid vector in existing index at {wanted['chunk_id']}")
        if dimensions is None:
            dimensions = len(vector)
        elif dimensions != len(vector):
            raise RAGError("Existing index contains inconsistent embedding dimensions")

    if section_metadata_added:
        index_bytes = json.dumps(chunks, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        _atomic_write(index_file, index_bytes)
    manifest = _make_index_manifest(corpus_manifest, corpus_hash, manifest_file, chunks, index_bytes)
    _atomic_write(index_manifest_file, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))
    return manifest


def validate_index(manifest_path=None, index_dir=None):
    """Verify corpus, source files, vectors and mappings before retrieval."""
    corpus_manifest, corpus_hash = _read_manifest(manifest_path)
    _, index_file, index_manifest_file = _paths(manifest_path, index_dir, corpus_manifest)
    documents = _load_documents(corpus_manifest)
    expected = _expected_chunks(documents)
    try:
        index_manifest = json.loads(index_manifest_file.read_text(encoding="utf-8"))
        index_bytes = index_file.read_bytes()
        stored_index = json.loads(index_bytes.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RAGError("Index or index manifest is missing/invalid; build the RAG index") from error

    required = {
        "index_format_version": INDEX_FORMAT_VERSION,
        "corpus_release": corpus_manifest["corpus_release"],
        "corpus_manifest_sha256": corpus_hash,
        "embedding_model": EMBEDDING_MODEL,
        "document_encoding": "RETRIEVAL_DOCUMENT",
        "query_encoding": "RETRIEVAL_QUERY",
        "metric": "cosine_similarity",
        "chunk_strategy": "markdown_section_aware_word_split",
        "chunk_max_chars": MAX_CHUNK_CHARS,
        "chunk_overlap_chars": CHUNK_OVERLAP_CHARS,
        "document_count": len(documents),
        "chunk_count": len(expected),
        "index_sha256": hashlib.sha256(index_bytes).hexdigest(),
    }
    for key, value in required.items():
        if index_manifest.get(key) != value:
            raise RAGError(f"Index is stale or inconsistent ({key}); rebuild it")
    # Earlier starter builds wrapped chunks in {"chunks": [...]}; normalize that format.
    chunks = stored_index.get("chunks") if isinstance(stored_index, dict) else stored_index
    if not isinstance(chunks, list) or len(chunks) != len(expected):
        raise RAGError("Index chunk count does not match corpus; rebuild it")

    dimensions = index_manifest.get("embedding_dimensions")
    if isinstance(dimensions, bool) or not isinstance(dimensions, int) or dimensions <= 0:
        raise RAGError("Index manifest has invalid embedding_dimensions")
    for actual, wanted in zip(chunks, expected):
        if any(actual.get(key) != wanted[key] for key in wanted):
            raise RAGError(f"Index mapping/text differs at {wanted['chunk_id']}; rebuild it")
        vector = actual.get("embedding")
        if not isinstance(vector, list) or len(vector) != dimensions or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in vector
        ):
            raise RAGError(f"Invalid vector at {wanted['chunk_id']}")
    return index_manifest, chunks


def filter_chunks_for_role(chunks, role):
    """Apply ACL before similarity ranking."""
    if role not in ROLE_ACCESS:
        raise RAGError("Unknown user role")
    return [chunk for chunk in chunks if chunk.get("access_level") in ROLE_ACCESS[role]]


def cosine_similarity(vector_a, vector_b):
    if len(vector_a) != len(vector_b):
        raise RAGError("Index embedding dimensions do not match the query")
    denom = math.sqrt(sum(a * a for a in vector_a) * sum(b * b for b in vector_b))
    return sum(a * b for a, b in zip(vector_a, vector_b)) / denom if denom else 0.0


def retrieve(question, role="customer", top_k=5, chunks=None):
    """Rank the role's chunks; pass `chunks` from an earlier validate_index() to skip re-validating per query."""
    if role not in ROLE_ACCESS:
        raise RAGError("Unknown user role")
    if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
        raise RAGError("top_k must be a positive integer")
    if not isinstance(question, str) or not question.strip():
        return []

    all_chunks = chunks if chunks is not None else validate_index()[1]
    allowed_chunks = filter_chunks_for_role(all_chunks, role)
    if not allowed_chunks:
        return []

    query_vector = embed_text(question.strip(), "RETRIEVAL_QUERY")
    ranked = sorted(
        ((cosine_similarity(query_vector, chunk["embedding"]), chunk) for chunk in allowed_chunks),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [
        {
            "chunk_id": chunk["chunk_id"],
            "doc_id": chunk["doc_id"],
            "title": chunk["title"],
            "source": chunk["source"],
            "version": chunk["version"],
            "access_level": chunk["access_level"],
            "section": chunk["section"],
            "text": chunk["text"],
            "score": score,
            "rank": rank,
        }
        for rank, (score, chunk) in enumerate(ranked[:top_k], start=1)
    ]


def _print_help():
    print("Usage: python -m src.rag.gemini_index {build|check|refresh-manifest}")


if __name__ == "__main__":
    import sys

    command = sys.argv[1] if len(sys.argv) == 2 else None
    try:
        if command == "build":
            result = build_index()
        elif command == "check":
            manifest, chunks = validate_index()
            result = {"status": "ok", "corpus_release": manifest["corpus_release"],
                      "documents": manifest["document_count"], "chunks": len(chunks),
                      "embedding_dimensions": manifest["embedding_dimensions"]}
        elif command == "refresh-manifest":
            result = refresh_index_manifest()
        else:
            _print_help()
            raise SystemExit(2)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except RAGError as error:
        print(f"RAG check failed: {error}")
        raise SystemExit(1)
