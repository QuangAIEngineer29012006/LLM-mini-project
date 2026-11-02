import hashlib
import re
from dataclasses import asdict, dataclass

from database.shop_db.corpus_files import parse_front_matter, read_normalized

CHUNK_CONFIG = {"strategy": "markdown_h2_section", "max_chars": 1200, "overlap_sentences": 1,
                "prefix": "doc_title + section_title"}
SECTION_RE = re.compile(r"(?m)^## +(.+)$")


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


def chunk_document(entry, repo_root, config=CHUNK_CONFIG):
    """Turn one manifest entry into section chunks with offsets into the LF-normalised source file."""
    text, _ = read_normalized(repo_root / entry["source_path"])
    front = parse_front_matter(text)
    if front.get("doc_id") != entry["doc_id"] or str(front.get("version")) != entry["version"]:
        raise ValueError(f"Front matter của {entry['source_path']} không khớp manifest")
    headings = list(SECTION_RE.finditer(text))
    if not headings:
        raise ValueError(f"{entry['source_path']} không có section ##")
    chunks = []
    for index, heading in enumerate(headings):
        body_start = heading.end() + 1
        body_end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = heading.group(1).strip()
        for offset, part in _split_long(text[body_start:body_end], config["max_chars"], config["overlap_sentences"]):
            body = part.strip()
            if not body:
                continue
            start = body_start + offset + (len(part) - len(part.lstrip()))
            chunk_text = f"{entry['title']} — {section}\n{body}"
            chunks.append(Chunk(
                chunk_id=f"{entry['doc_id']}@{entry['version']}#{len(chunks) + 1:02d}",
                doc_id=entry["doc_id"], title=entry["title"], section=section, source=entry["source_path"],
                version=entry["version"], access_level=entry["access_level"], doc_type=entry["doc_type"],
                char_start=start, char_end=start + len(body), skus=list(entry.get("skus", [])),
                product_ids=list(entry.get("product_ids", [])), text=chunk_text,
                sha256=hashlib.sha256(chunk_text.encode()).hexdigest()))
    return chunks
