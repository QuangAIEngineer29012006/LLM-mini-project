import re
from dataclasses import dataclass

import numpy as np

from database.shop_db.corpus_service import allowed_access_levels
from database.shop_db.text_utils import normalize

SKU_RE = re.compile(r"\b[A-Z]{3}-[A-Z0-9]{2,4}-[A-Z0-9]{1,3}\b", re.I)
# Business-condition questions must be answered from the policy itself, not only from FAQ/guide wording.
POLICY_CUES = ("doi tra", "doi y", "doi size", "doi mau", "bao hanh", "hoan tien", "huy don", "thieu hang",
               "hu hong", "giao hang", "van chuyen", "phi ship", "thanh toan", "ngap nuoc")
SKU_BOOST = 0.2


@dataclass
class Hit:
    chunk: object
    score: float
    rank: int

    def debug(self):
        c = self.chunk
        return {"rank": self.rank, "score": round(self.score, 4), "chunk_id": c.chunk_id, "doc_id": c.doc_id,
                "version": c.version, "access_level": c.access_level, "section": c.section}


def retrieve(bundle, embedder, query, role, k=5):
    """Rank only the chunks the role may read: other access levels are never loaded into the candidate set."""
    levels = allowed_access_levels(role)
    chunks = [c for level in levels for c in bundle.chunks[level]]
    matrices = [bundle.vectors[level] for level in levels if bundle.vectors[level].size]
    if not chunks or not matrices or not normalize(query):
        return []
    scores = np.vstack(matrices) @ embedder.embed_query(query)
    skus = {s.upper() for s in SKU_RE.findall(query)}
    if skus:
        scores = scores + np.array([SKU_BOOST if skus & set(c.skus) else 0.0 for c in chunks], dtype=np.float32)
    order = np.argsort(-scores, kind="stable")[:k]
    return [Hit(chunks[i], float(scores[i]), rank) for rank, i in enumerate(order, 1)]


def select_context(hits, query, min_score, max_chunks=4, max_chars=3200):
    """Keep evidence above the cut-off; ensure a policy chunk is present for business-condition questions."""
    kept = [h for h in hits if h.score >= min_score]
    text = normalize(query)
    if kept and any(cue in text for cue in POLICY_CUES) and not any(h.chunk.doc_type == "policy" for h in kept[:max_chunks]):
        policy = next((h for h in kept if h.chunk.doc_type == "policy"), None)
        if policy:
            kept = kept[:max_chunks - 1] + [policy]
    context, used = [], 0
    for hit in kept[:max_chunks]:
        if used + len(hit.chunk.text) > max_chars:
            break
        context.append(hit)
        used += len(hit.chunk.text)
    return context
