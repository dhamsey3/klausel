"""Central configuration, read from environment variables / `.env`.

Offline mode for Hugging Face / ZenML is enforced in `klausel/__init__.py`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _project_root() -> Path:
    """Repo root for an editable install; otherwise $KLAUSEL_HOME or the working directory."""
    if home := os.environ.get("KLAUSEL_HOME"):
        return Path(home).expanduser().resolve()
    src_root = Path(__file__).resolve().parents[2]
    return src_root if (src_root / "pyproject.toml").exists() else Path.cwd()


PROJECT_ROOT = _project_root()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env", env_file_encoding="utf-8", extra="ignore"
    )

    # MinIO via standard boto3 env vars
    aws_access_key_id: str = "klausel-admin"
    aws_secret_access_key: str = "change-me-local-only"
    aws_default_region: str = "eu-central-1"
    aws_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "legal-docs-raw"
    s3_prefix: str = ""

    # Qdrant
    qdrant_url: str = "http://localhost:6333"
    qdrant_api_key: str | None = None
    qdrant_collection: str = "legal_docs_de"

    # Embeddings
    embedding_model_name: str = "intfloat/multilingual-e5-small"
    # Exact Hugging Face commit, so every install gets identical weights.
    embedding_model_revision: str = "614241f622f53c4eeff9890bdc4f31cfecc418b3"
    embedding_model_dir: Path = PROJECT_ROOT / "models" / "multilingual-e5-small"
    embedding_device: str = "auto"  # auto | cpu | cuda | mps
    embedding_batch_size: int = 32

    # Chunking / privacy
    chunk_size: int = Field(1000, gt=100)
    chunk_overlap: int = Field(150, ge=0)
    redact_pii: bool = True

    # Ollama
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout_s: float = 300.0
    retrieval_top_k: int = 5

    @property
    def resolved_model_dir(self) -> Path:
        p = self.embedding_model_dir
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()
