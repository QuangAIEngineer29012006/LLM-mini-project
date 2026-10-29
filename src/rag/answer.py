import json
import math
import re
from collections import Counter

from pydantic import ValidationError

from database.shop_db.text_utils import normalize
from src.llm_client import LLMError

from .embedder import STOPWORDS
from .prompts import GeneratedAnswer, build_answer_prompt

QUESTION_WORDS = {"bao", "lau", "nhieu", "nao", "sao", "lam", "phai", "giup", "vay", "khong", "duoc", "co",
                  "bi", "thi", "luc", "sau", "truoc", "neu"}
MIN_COVERAGE = 0.5
AMOUNT_CUES = (" bao lau ", " bao nhieu ", " may ngay ", " may thang ", " thoi han ", " toi da ", " muc ")


def content_tokens(text):
    return list(dict.fromkeys(t for t in normalize(text).split()
                              if len(t) > 1 and t not in STOPWORDS and t not in QUESTION_WORDS))


def _sentences(chunk):
    body = chunk.text.split("\n", 1)[1] if "\n" in chunk.text else chunk.text
    parts = re.split(r"\n+|(?<=[.!?])\s+", body)
    return [p.strip().lstrip("-• ").strip() for p in parts if len(p.strip()) > 20 and not p.strip().startswith("|")]


class FakeGenerator:
    """Offline extractive answerer: copies the best-matching sentences from the context and cites them.

    Sentence scoring weights query terms by IDF over the readable chunks and, in product sheets, discounts terms
    from the title, so a sentence about washing beats one that merely repeats the product name.
    """
    name = "fake-extractive-v2"

    def __init__(self, document_frequency, chunk_count, weighted=True):
        self.df = document_frequency
        self.n = chunk_count
        self.weighted = weighted

    def weight(self, token, title_tokens):
        if not self.weighted:
            return 1.0
        idf = math.log((self.n + 1) / (self.df.get(token, 0) + 1))
        return idf * (0.2 if token in title_tokens else 1.0)

    def generate(self, question, context):
        tokens = content_tokens(question)
        unknown = [t for t in tokens if t not in self.df and len(t) >= 3 and not any(ch.isdigit() for ch in t)]
        context_tokens = set(normalize(" ".join(h.chunk.text for h in context)).split())
        coverage = sum(t in context_tokens for t in tokens) / len(tokens) if tokens else 0
        if not tokens or unknown or coverage < MIN_COVERAGE:
            missing = ("Tài liệu chưa đề cập: " + ", ".join(unknown)) if unknown else "Tài liệu chưa có thông tin trả lời câu hỏi này."
            return {"status": "insufficient_evidence", "answer": "", "citation_chunk_ids": [], "missing_information": missing}
        asks_amount = any(cue in f" {normalize(question)} " for cue in AMOUNT_CUES)

        def score(sentence, rank, title_tokens):
            words = set(normalize(sentence).split())
            matched = [t for t in tokens if t in words]
            if not matched:
                return 0
            value = sum(self.weight(t, title_tokens) for t in matched)
            scale = value / len(matched) if self.weighted else 1.0
            return value - 0.3 * rank * scale + (0.8 * scale if asks_amount and any(ch.isdigit() for ch in sentence) else 0)

        # Only product sheets repeat their subject in every sentence; policy titles list the topics they answer.
        scored = [(hit, [(score(s, rank, set(normalize(hit.chunk.title).split()) if hit.chunk.doc_type == "product_spec" else set()), s)
                         for s in _sentences(hit.chunk)])
                  for rank, hit in enumerate(context)]
        best_hit, best_sentences = max(scored, key=lambda item: max((s for s, _ in item[1]), default=0))
        best = max((s for s, _ in best_sentences), default=0)
        if best <= 0:
            return {"status": "insufficient_evidence", "answer": "", "citation_chunk_ids": [],
                    "missing_information": "Không tìm thấy câu phù hợp trong tài liệu."}
        # A section reads as one unit: keep its matching sentences in document order (at most three).
        picked = [(best_hit.chunk.chunk_id, s) for value, s in best_sentences if value > 0][:3]
        covered = {t for _, s in picked for t in tokens if t in normalize(s).split()}
        for hit, sentences in scored:
            if hit is best_hit or hit.chunk.doc_id == best_hit.chunk.doc_id:
                continue
            value, sentence = max(sentences, default=(0, ""))
            if value >= 0.8 * best and {t for t in tokens if t in normalize(sentence).split()} - covered:
                picked.append((hit.chunk.chunk_id, sentence))
                break
        picked = [(cid, s.rstrip(":") + ".") if s.endswith(":") else (cid, s) for cid, s in picked]
        answer = " ".join(s if s.endswith((".", "!", "?")) else s + "." for _, s in picked)
        return {"status": "answered", "answer": answer, "citation_chunk_ids": list(dict.fromkeys(c for c, _ in picked)),
                "missing_information": ""}


def document_frequency(chunks):
    return Counter(t for c in chunks for t in set(normalize(c.text).split()))


class GeminiGenerator:
    name = "gemini"

    def __init__(self, client):
        self.client = client

    def generate(self, question, context):
        system, prompt = build_answer_prompt(question, context)
        result = self.client.complete(system, prompt, GeneratedAnswer.model_json_schema())
        try:
            return GeneratedAnswer.model_validate(json.loads(result.text)).model_dump()
        except (ValueError, ValidationError):
            raise LLMError("llm_response") from None
