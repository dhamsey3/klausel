"""Local sentence-embedding model (loaded strictly from disk).

The model is fetched once, ahead of time, by `scripts/download_model.py`.
At runtime we pass `local_files_only=True` and HF offline mode is forced in
`klausel.config`, so nothing is ever requested from huggingface.co.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from klausel.config import get_settings


def _resolve_device(pref: str) -> str:
    if pref != "auto":
        return pref
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class LocalEmbedder:
    """Wraps SentenceTransformer and applies E5-style `query:` / `passage:` prefixes."""

    def __init__(
        self, model_dir: Path, model_name: str, device: str = "auto", batch_size: int = 32
    ):
        if not (model_dir / "config.json").exists():
            raise FileNotFoundError(
                f"Embedding model not found at {model_dir}. "
                "Run `python scripts/download_model.py` once while online."
            )
        from sentence_transformers import SentenceTransformer

        self.device = _resolve_device(device)
        self.model = SentenceTransformer(str(model_dir), device=self.device, local_files_only=True)
        self.batch_size = batch_size
        self._e5 = "e5" in model_name.lower()

    @property
    def dimension(self) -> int:
        return int(self.model.get_sentence_embedding_dimension())

    def _encode(self, texts: list[str]) -> np.ndarray:
        return self.model.encode(
            texts,
            batch_size=self.batch_size,
            normalize_embeddings=True,  # cosine similarity == dot product
            convert_to_numpy=True,
            show_progress_bar=len(texts) > 256,
        )

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._encode([f"passage: {t}" if self._e5 else t for t in texts])

    def embed_query(self, text: str) -> np.ndarray:
        return self._encode([f"query: {text}" if self._e5 else text])[0]


@lru_cache
def get_embedder() -> LocalEmbedder:
    s = get_settings()
    return LocalEmbedder(
        model_dir=s.resolved_model_dir,
        model_name=s.embedding_model_name,
        device=s.embedding_device,
        batch_size=s.embedding_batch_size,
    )
