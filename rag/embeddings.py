"""
BAAI/bge-small-en-v1.5 embedding wrapper.
EXPECTED_DIM=384 FIXED — changing requires Qdrant collection rebuild.
"""
from __future__ import annotations
import numpy as np
from sentence_transformers import SentenceTransformer

EXPECTED_DIM = 384  # LOCKED — do NOT change without rebuilding Qdrant collection

class EmbeddingModel:
    def __init__(self):
        self._model = SentenceTransformer("BAAI/bge-small-en-v1.5")

    def _assert_dim(self, v: np.ndarray):
        if v.shape[-1] != EXPECTED_DIM:
            raise RuntimeError(f"Embedding dim mismatch: got {v.shape[-1]}, expected {EXPECTED_DIM}")

    def encode(self, text: str) -> np.ndarray:
        v = self._model.encode(text, normalize_embeddings=True).astype("float32")
        self._assert_dim(v)
        return v

    def encode_batch(self, texts: list[str], batch_size: int = 64) -> np.ndarray:
        show = len(texts) > 100
        vecs = self._model.encode(texts, batch_size=batch_size,
                                  normalize_embeddings=True,
                                  show_progress_bar=show).astype("float32")
        self._assert_dim(vecs[0])
        return vecs

embedding_model = EmbeddingModel()
