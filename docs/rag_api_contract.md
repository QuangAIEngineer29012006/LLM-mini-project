# TV2 RAG handoff contract

TV2 provides a Python retrieval/answer helper. TV3 owns the HTTP endpoint, chat routing, and authentication.

## Call from the backend workflow

```python
from backend.knowledge_route import answer_knowledge_question

result = answer_knowledge_question(
    question=customer_message,
    role=authenticated_session_role,
)
```

`authenticated_session_role` must come from backend authentication (`customer`, `staff`, or `admin`), never from the customer's message or an untrusted request field.

## Return shape

```json
{
  "status": "answered | insufficient_evidence | access_denied",
  "answer": "Vietnamese answer or a safe limitation message",
  "citations": [
    {
      "chunk_id": "DOC-PRD-001:3",
      "doc_id": "DOC-PRD-001",
      "source": "data_config/corpus/products/prd_01_ao_thun_basic_cotton.md",
      "version": "1.0"
    }
  ],
  "missing_information": ""
}
```

`citations` only contains chunks retrieved for the supplied role. `access_denied` returns no restricted citation or document text. `RAGError` indicates the index/corpus is missing, stale, invalid, or a provider call failed; TV3 should convert it into the backend's standard error response.

## Retrieval-only interface

For workflows that assemble their own answer, TV3 may call:

```python
from src.rag import retrieve

chunks = retrieve(question, role=authenticated_session_role, top_k=8)
```

Each result includes `chunk_id`, `doc_id`, `title`, `source`, `version`, `access_level`, `section`, `text`, `score`, and `rank`. Role filtering happens before similarity ranking.

## TV2 maintenance commands

From the project folder, using the project virtual environment:

```powershell
& ".\LLM RAG\Scripts\python.exe" scripts\check_rag.py
& ".\LLM RAG\Scripts\python.exe" -m src.rag build
& ".\LLM RAG\Scripts\python.exe" -m src.rag check
```

The local checker makes no Gemini calls. Rebuild after corpus content, release, embedding model, or chunking settings change.
