import hashlib
import time
from collections import OrderedDict
from urllib.parse import quote

import numpy as np
import requests

from database.shop_db.text_utils import normalize
from src.llm_client import LLMError
from src.quota import DailyBudget, DailyLimitReached

# Function words that carry no retrieval signal once accents are stripped. "bao" is kept on purpose:
# it starts "bảo hành", and bigrams still need it.
STOPWORDS = {"la", "cua", "va", "cho", "toi", "minh", "ban", "co", "khong", "duoc", "nhung", "cac", "mot",
             "nay", "do", "thi", "se", "da", "dang", "voi", "trong", "tren", "khi", "neu", "de", "hay",
             "hoac", "ve", "theo", "tu", "den", "gi", "nao", "the", "nhu", "vay", "a", "oi", "em", "anh",
             "chi", "shop", "ma", "rat", "nhe", "can", "muon", "biet", "hoi"}


def features(text):
    tokens = normalize(text).split()
    feats = [(t, 1.0) for t in tokens if t not in STOPWORDS]
    feats += [(f"{a}_{b}", 1.5) for a, b in zip(tokens, tokens[1:])]
    feats += [(f"#{t[i:i + 3]}", 0.3) for t in tokens if len(t) > 3 for i in range(len(t) - 2)]
    return feats


class FakeEmbedder:
    """Deterministic hashed bag-of-ngrams over accent-free text; lexical, offline, reproducible."""
    provider = "fake"
    model = "hashed-ngram-v1"
    revision = "1"
    dimension = 512
    query_encoding = document_encoding = "normalize(lower, no accents) -> unigram + bigram + char-trigram, signed hashing"
    # Cosine cut-off for context; scores are only comparable within one embedding model.
    min_score = 0.12

    def _embed(self, text):
        vector = np.zeros(self.dimension, dtype=np.float32)
        for feature, weight in features(text):
            digest = int.from_bytes(hashlib.md5(feature.encode()).digest()[:8], "big")
            vector[digest % self.dimension] += weight if digest >> 63 else -weight
        norm = np.linalg.norm(vector)
        return vector / norm if norm else vector

    def embed_documents(self, chunks):
        return np.stack([self._embed(c.text) for c in chunks]) if chunks else np.zeros((0, self.dimension), np.float32)

    def embed_query(self, text):
        return self._embed(text)


class GeminiEmbedder:
    provider = "gemini"
    revision = "api"
    query_encoding = "taskType=RETRIEVAL_QUERY"
    document_encoding = "taskType=RETRIEVAL_DOCUMENT, title=doc title"
    # Chosen on the dev split: answerable top-1 >= 0.718, no-evidence top-1 <= 0.613.
    min_score = 0.65

    def __init__(self, settings):
        self.settings = settings
        self.model = settings.rag_embedding_model
        self.dimension = settings.rag_embedding_dimension
        self.budget = DailyBudget(settings.llm_usage_path, settings.llm_daily_limit) if settings.llm_usage_path else None
        self.query_cache = OrderedDict()

    def _call(self, requests_payload):
        if self.budget:
            try:
                self.budget.reserve(self.model)
            except DailyLimitReached:
                raise LLMError("llm_daily_limit") from None
        url = ("https://generativelanguage.googleapis.com/v1beta/models/" + quote(self.model, safe="-")
               + ":batchEmbedContents")
        try:
            response = requests.post(url, headers={"x-goog-api-key": self.settings.api_key},
                                     json={"requests": requests_payload}, timeout=self.settings.llm_timeout,
                                     allow_redirects=False)
        except (requests.Timeout, requests.ConnectionError):
            raise LLMError("llm_timeout") from None
        if response.status_code == 429:
            raise LLMError("llm_rate_limit")
        if response.status_code != 200:
            raise LLMError("llm_auth" if response.status_code in {401, 403} else "llm_request")
        try:
            vectors = np.array([e["values"] for e in response.json()["embeddings"]], dtype=np.float32)
        except (KeyError, TypeError, ValueError):
            raise LLMError("llm_response") from None
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        return vectors / np.where(norms == 0, 1, norms)

    def _request(self, text, task, title=None):
        item = {"model": f"models/{self.model}", "content": {"parts": [{"text": text}]}, "taskType": task,
                "outputDimensionality": self.dimension}
        if title:
            item["title"] = title
        return item

    def embed_documents(self, chunks, batch=25, retries=4, wait=30):
        """Offline index build: small batches, and wait out per-minute limits (counted per text) instead of failing."""
        out = []
        for i in range(0, len(chunks), batch):
            payload = [self._request(c.text, "RETRIEVAL_DOCUMENT", c.title) for c in chunks[i:i + batch]]
            for attempt in range(retries + 1):
                try:
                    out.append(self._call(payload))
                    break
                except LLMError as err:
                    if err.code != "llm_rate_limit" or attempt == retries:
                        raise
                    time.sleep(wait)
        return np.vstack(out) if out else np.zeros((0, self.dimension), np.float32)

    def embed_query(self, text):
        key = normalize(text)
        if key not in self.query_cache:
            self.query_cache[key] = self._call([self._request(text, "RETRIEVAL_QUERY")])[0]
            while len(self.query_cache) > 512:
                self.query_cache.popitem(last=False)
        return self.query_cache[key]


def make_embedder(settings, provider=None):
    return GeminiEmbedder(settings) if (provider or settings.rag_embedding_provider) == "gemini" else FakeEmbedder()
