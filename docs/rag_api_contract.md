# TV2 RAG handoff contract

TV2 provides the Gemini index and retrieval (`src/rag/gemini_index.py`). TV3 owns the HTTP endpoint (`/api/knowledge`), chat routing, authentication, answer generation and citation checks (`src/rag/service.py`).

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
  "status": "answered | insufficient_evidence | access_denied | handoff",
  "answer": "Vietnamese answer or a safe limitation message",
  "citations": [
    {
      "chunk_id": "DOC-PRD-001:3",
      "doc_id": "DOC-PRD-001",
      "source": "data_config/corpus/products/prd_01_ao_thun_basic_cotton.md",
      "version": "1.0",
      "title": "Áo thun basic cotton — thông số, biến thể và bảo quản",
      "section": "Chất liệu và form"
    }
  ],
  "missing_information": ""
}
```

`citations` only contains chunks retrieved for the supplied role, and each one was checked against the active corpus release (file exists, sha256, version). `access_denied` returns no restricted citation or document text; it is decided from the question before retrieval. `handoff` means an unsafe request (e.g. asking to ignore policies). `RAGError` indicates the index/corpus is missing, stale, invalid, or a provider call failed; the HTTP API returns it as `status: "error"`.

## Retrieval-only interface

For workflows that assemble their own answer, TV3 may call:

```python
from src.rag.gemini_index import retrieve, validate_index

_, chunks = validate_index()          # once; validates corpus, hashes, mapping and vectors
hits = retrieve(question, role=authenticated_session_role, top_k=8, chunks=chunks)
```

Each result includes `chunk_id`, `doc_id`, `title`, `source`, `version`, `access_level`, `section`, `text`, `score`, and `rank`. Role filtering happens before similarity ranking. Without `chunks`, `retrieve()` validates the index on every call.

## Index location

Each corpus release has its own folder, `artifacts/index/<release>-gemini/` (`rag_index.json` + `index_manifest.json`), so an admin can activate an older release without re-embedding. `artifacts/index_manifest.json` points at the active one; `KnowledgeService` loads it through `src/rag/gemini_bundle.py`.

## TV2 maintenance commands

From the project folder, using the project virtual environment:

```powershell
& ".\LLM RAG\Scripts\python.exe" scripts\check_rag.py
& ".\LLM RAG\Scripts\python.exe" -m src.rag.gemini_index build
& ".\LLM RAG\Scripts\python.exe" -m src.rag.gemini_index check
```

`build` and `check` use `RAG_CORPUS_MANIFEST` (default v1.1) and that release's folder. The local checker makes no Gemini calls. Rebuild after corpus content, release, embedding model, or chunking settings change.
