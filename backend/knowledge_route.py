"""Python entry point promised in docs/rag_api_contract.md, for callers outside HTTP (e.g. scripts/check_rag.py).

/api/knowledge and the chat route use the same KnowledgeService. `role` must come from backend authentication.
"""
from functools import lru_cache

from database.shop_db.db import connect
from src.llm_client import make_client
from src.rag.gemini_index import RAGError
from src.rag.service import KnowledgeService

from .config import Settings
from .storage import initialize


@lru_cache(maxsize=1)
def _service():
    settings = Settings.from_env()
    service = KnowledgeService(settings, make_client(settings))
    initialize(settings.db_path, service.manifest_path)
    return settings, service


def answer_knowledge_question(question, role):
    """Return {status, answer, citations, missing_information}; raise RAGError when the index cannot answer."""
    settings, service = _service()
    conn = connect(settings.db_path)
    try:
        service.check_release(conn)
        result = service.answer(conn, question, role)
    finally:
        conn.close()
    if result["status"] == "error":
        raise RAGError(result["missing_information"] or "Knowledge index is not ready")
    return {key: result[key] for key in ("status", "answer", "citations", "missing_information")}
