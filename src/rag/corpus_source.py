"""Corpus text for indexing, read from the sections the database extracted from each PDF at sync time."""
import re
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path

from database.shop_db.corpus_seed import ensure_corpus_seeded
from database.shop_db.db import connect, get_db_path

TABLE_ROW = re.compile(r"\S {3,}\S")
BULLET = re.compile(r"^(?:•\s*|-\s+)")
SENTENCE_END = (".", ":", ";", "!", "?")


class CorpusTextError(Exception):
    pass


def unwrap(text):
    """Join lines the PDF wrapped mid-sentence; bullets, table rows and lines that end a sentence stay separate."""
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        bullet = BULLET.match(line)
        if bullet:
            line = "- " + line[bullet.end():]
        previous = lines[-1] if lines else None
        if (previous is not None and not bullet and not previous.endswith(SENTENCE_END)
                and not TABLE_ROW.search(previous) and not TABLE_ROW.search(line)):
            lines[-1] = f"{previous} {line}"
        else:
            lines.append(line)
    return "\n".join(lines)


def load_documents(manifest, db_path=None):
    """Return each manifest document with its DB sections, in manifest order.

    Sections exist only for versions a sync has stored, so a release must be synced once before it is indexed.
    The DB hash must equal the manifest hash, so the text comes from the same PDF the manifest names.
    """
    conn = connect(db_path or get_db_path())
    try:
        documents = []
        for entry in manifest["documents"]:
            version = conn.execute(
                "SELECT id, content_sha256 FROM corpus_document_versions WHERE doc_id = ? AND version = ?",
                (entry["doc_id"], entry["version"])).fetchone()
            if version is None:
                raise CorpusTextError(f"{entry['doc_id']} v{entry['version']} chưa có trong DB; "
                                      f"hãy sync release {manifest['corpus_release']} trước khi build index")
            if version["content_sha256"] != entry["content_sha256"]:
                raise CorpusTextError(f"Hash của {entry['doc_id']} v{entry['version']} trong DB khác manifest")
            rows = conn.execute(
                "SELECT section_title, section_text, char_start, char_end FROM corpus_document_sections"
                " WHERE version_id = ? ORDER BY section_index", (version["id"],)).fetchall()
            if not rows:
                raise CorpusTextError(f"{entry['doc_id']} v{entry['version']} chưa có section trong DB")
            documents.append({**entry, "sections": [
                {"title": r["section_title"], "text": unwrap(r["section_text"]),
                 "char_start": r["char_start"], "char_end": r["char_end"]} for r in rows]})
        return documents
    except sqlite3.Error as err:
        # A DB not yet migrated or synced (the app loads its index once before startup syncs) has no corpus tables.
        raise CorpusTextError(f"DB chưa có dữ liệu corpus: {err}") from None
    finally:
        conn.close()


@contextmanager
def release_db(manifest_path):
    """Yield a throwaway DB with one release synced, so a build reads DB-extracted text without touching the app DB."""
    with tempfile.TemporaryDirectory() as folder:
        path = str(Path(folder) / "corpus.db")
        conn = connect(path)
        try:
            ensure_corpus_seeded(conn, Path(manifest_path))
        finally:
            conn.close()
        yield path
