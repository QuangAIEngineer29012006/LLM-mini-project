"""Local, no-API checks for TV2's RAG corpus, index, chunking and ACL filter."""
from collections import Counter
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.rag import (
    RAGError,
    filter_chunks_for_role,
    is_restricted_topic,
    load_documents,
    retrieve,
    validate_index,
)
from backend.knowledge_route import answer_knowledge_question


def main():
    index_manifest, chunks = validate_index()
    documents = load_documents()
    levels = Counter(chunk["access_level"] for chunk in chunks)

    customer_chunks = filter_chunks_for_role(chunks, "customer")
    staff_chunks = filter_chunks_for_role(chunks, "staff")
    admin_chunks = filter_chunks_for_role(chunks, "admin")
    assert all(chunk["access_level"] == "public" for chunk in customer_chunks)
    assert all(chunk["access_level"] in {"public", "staff"} for chunk in staff_chunks)
    assert len(admin_chunks) == len(chunks)

    # Exercise the real retrieval path with a local vector; this makes no API call.
    with patch("src.rag.embed_text", return_value=chunks[0]["embedding"]):
        ranked = retrieve("local smoke query", role="customer", top_k=5)
    assert len(ranked) == 5
    assert [hit["rank"] for hit in ranked] == [1, 2, 3, 4, 5]
    assert all(hit["access_level"] == "public" for hit in ranked)

    try:
        filter_chunks_for_role(chunks, "guest")
    except RAGError:
        pass
    else:
        raise AssertionError("Unknown roles must be rejected")

    return_chunks = [chunk for chunk in chunks if chunk["doc_id"] == "DOC-POL-RETURN"]
    assert any("14 ngày" in chunk["text"] for chunk in return_chunks)
    assert any("CAP-NVY-F" in chunk["text"] for chunk in return_chunks)
    assert is_restricted_topic("hạn mức hỗ trợ phí nội bộ là bao nhiêu?", "customer")
    assert not is_restricted_topic("giao hàng hỏa tốc trong 2 giờ không?", "customer")
    denied = answer_knowledge_question(
        "Khách hàng được biết hạn mức hỗ trợ phí nội bộ là bao nhiêu?", role="customer"
    )
    assert denied["status"] == "access_denied" and not denied["citations"]

    print("RAG local checks: PASS")
    print(f"Corpus release: {index_manifest['corpus_release']} ({len(documents)} documents)")
    print(f"Index: {len(chunks)} chunks, {index_manifest['embedding_dimensions']} dimensions")
    print(f"Chunks by access: {dict(levels)}")
    print("ACL and ranked retrieval: customer/staff/admin PASS; unknown role rejected")
    print("Policy chunking and restricted-topic checks: PASS")
    print("No Gemini API calls were made by this check.")


if __name__ == "__main__":
    main()
