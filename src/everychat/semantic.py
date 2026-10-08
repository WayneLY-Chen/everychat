"""Optional local semantic search. Install with: pip install "everychat[semantic]"

Embeddings come from a small multilingual model that runs on CPU through fastembed,
so nothing leaves the machine and there is no API key.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from .db import OVERFETCH, Database, Hit, _one_per_conversation

# Hugging Face warns about symlinks on Windows without developer mode; the cache works anyway.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
MAX_CHARS = 2000  # the model truncates far earlier anyway; this bounds tokenizer work
BATCH = 64


class SemanticUnavailable(RuntimeError):
    pass


def _load():
    try:
        import numpy as np
        from fastembed import TextEmbedding
    except ImportError as exc:
        raise SemanticUnavailable(
            'Semantic search needs extra packages: pip install "everychat[semantic]"'
        ) from exc
    return np, TextEmbedding(model_name=MODEL)


def embed_missing(db: Database, progress: Callable[[int, int], None] | None = None) -> int:
    """Embed every message that has no vector yet. Returns how many were embedded."""
    np, model = _load()
    pending = db.messages_without_embedding(MODEL)
    total = len(pending)
    for start in range(0, total, BATCH):
        batch = pending[start : start + BATCH]
        texts = [row["content"][:MAX_CHARS] for row in batch]
        vectors = model.embed(texts)
        pairs = zip(batch, vectors, strict=False)
        db.store_embeddings(MODEL, [(row["id"], _normalize(np, v).tobytes()) for row, v in pairs])
        db.commit()
        if progress:
            progress(min(start + BATCH, total), total)
    return total


def search(db: Database, query: str, source: str | None = None, limit: int = 20) -> list[Hit]:
    np, model = _load()
    rows = db.all_embeddings(MODEL, source)
    if not rows:
        return []
    ids = [row["message_id"] for row in rows]
    matrix = np.stack([np.frombuffer(row["vector"], dtype=np.float32) for row in rows])
    query_vec = _normalize(np, next(iter(model.embed([query]))))
    scores = matrix @ query_vec
    best = np.argsort(-scores)[: limit * OVERFETCH]
    hits = db.hits_for_messages([ids[i] for i in best])
    results = []
    for i in best:
        hit = hits.get(ids[i])
        if hit:
            hit.score = float(scores[i])
            results.append(hit)
    return _one_per_conversation(results)[:limit]


def _normalize(np, vector):
    vector = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(vector)
    return vector / norm if norm else vector
