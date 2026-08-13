"""Vector store (step 4: store embeddings; step 5: retrieve relevant chunks).

Uses a FAISS inner-product index when faiss is installed (vectors are
L2-normalized, so inner product == cosine similarity), and falls back to a
NumPy cosine search otherwise — so the app runs even before ``pip install
faiss-cpu``. Same interface either way.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

try:
    import faiss  # type: ignore
    _HAS_FAISS = True
except Exception:  # noqa: BLE001 - any import problem -> numpy fallback
    _HAS_FAISS = False


@dataclass
class Retrieved:
    text: str
    score: float
    source: str      # which document the chunk came from


def _normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return mat / norms


@dataclass
class VectorStore:
    """An in-memory vector store. ``backend`` reports which engine is live so
    the UI/README can state it honestly."""

    dim: int
    backend: str = field(init=False)
    _texts: list[str] = field(default_factory=list)
    _sources: list[str] = field(default_factory=list)
    _matrix: np.ndarray | None = field(default=None)   # numpy fallback
    _index: object = field(default=None)               # faiss index

    def __post_init__(self) -> None:
        self.backend = "faiss" if _HAS_FAISS else "numpy"
        if _HAS_FAISS:
            self._index = faiss.IndexFlatIP(self.dim)

    def add(self, chunks: list[str], vectors: list[list[float]], source: str) -> None:
        """Store chunk texts + their embeddings (step 4)."""
        if not chunks:
            return
        vecs = _normalize(np.asarray(vectors, dtype="float32"))
        self._texts.extend(chunks)
        self._sources.extend([source] * len(chunks))
        if _HAS_FAISS:
            self._index.add(vecs)
        else:
            self._matrix = (vecs if self._matrix is None
                            else np.vstack([self._matrix, vecs]))

    def search(self, query_vector: list[float], k: int = 4) -> list[Retrieved]:
        """Return the top-k most similar chunks to the query (step 5)."""
        if not self._texts:
            return []
        q = _normalize(np.asarray([query_vector], dtype="float32"))
        k = min(k, len(self._texts))
        if _HAS_FAISS:
            scores, idxs = self._index.search(q, k)
            pairs = zip(idxs[0].tolist(), scores[0].tolist())
        else:
            sims = (self._matrix @ q[0])
            order = np.argsort(-sims)[:k]
            pairs = ((int(i), float(sims[i])) for i in order)
        return [Retrieved(text=self._texts[i], score=round(s, 4),
                          source=self._sources[i]) for i, s in pairs]

    @property
    def size(self) -> int:
        return len(self._texts)
