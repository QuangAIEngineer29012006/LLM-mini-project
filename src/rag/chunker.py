import hashlib
import re
from dataclasses import asdict, dataclass

CHUNK_CONFIG = {"strategy": "db_section", "max_chars": 1200, "overlap_sentences": 1,
                "prefix": "doc_title + section_title"}


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    title: str
    section: str
    source: str
    version: str
    access_level: str
    doc_type: str
    char_start: int
    char_end: int
    skus: list
    product_ids: list
    text: str
    sha256: str

    def to_dict(self):
        return asdict(self)


def _split_long(body, max_chars, overlap):
    """Split an over-long section on paragraph/sentence boundaries; returns (offset, text) pairs."""
    if len(body) <= max_chars:
        return [(0, body)]
    sentences = [(m.start(), m.group()) for m in re.finditer(r"[^.!?\n]+[.!?]?\s*", body)]
    parts, current, start = [], [], 0
    for offset, sentence in sentences:
        if current and sum(len(s) for _, s in current) + len(sentence) > max_chars:
            parts.append((start, "".join(s for _, s in current)))
            current = current[-overlap:] if overlap else []
            start = current[0][0] if current else offset
        if not current:
            start = offset
        current.append((offset, sentence))
    if current:
        parts.append((start, "".join(s for _, s in current)))
    return parts


def chunk_document(document, config=CHUNK_CONFIG):
    """Turn one document from corpus_source.load_documents into chunks, one or more per DB section.

    char_start/char_end are the section's range in the DB's content_text; a split section shares that range.
    """
    chunks = []
    for section in document["sections"]:
        for _, part in _split_long(section["text"], config["max_chars"], config["overlap_sentences"]):
            body = part.strip()
            if not body:
                continue
            chunk_text = f"{document['title']} — {section['title']}\n{body}"
            chunks.append(Chunk(
                chunk_id=f"{document['doc_id']}@{document['version']}#{len(chunks) + 1:02d}",
                doc_id=document["doc_id"], title=document["title"], section=section["title"],
                source=document["source_path"], version=document["version"], access_level=document["access_level"],
                doc_type=document["doc_type"], char_start=section["char_start"], char_end=section["char_end"],
                skus=list(document.get("skus", [])), product_ids=list(document.get("product_ids", [])),
                text=chunk_text, sha256=hashlib.sha256(chunk_text.encode()).hexdigest()))
    return chunks
