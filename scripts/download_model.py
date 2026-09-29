"""One-time, online step: fetch the embedding model into ./models.

This is the ONLY command in the project that talks to the internet. After it
finishes, everything runs with HF_HUB_OFFLINE=1. For a fully air-gapped host,
run this on a connected machine and copy the ./models folder across.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# Must be allowed online for this script only.
os.environ["HF_HUB_OFFLINE"] = "0"
os.environ["TRANSFORMERS_OFFLINE"] = "0"
os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

from huggingface_hub import snapshot_download  # noqa: E402

from klausel.config import get_settings  # noqa: E402


def main() -> None:
    s = get_settings()
    target = s.resolved_model_dir
    target.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {s.embedding_model_name} -> {target}")
    snapshot_download(
        repo_id=s.embedding_model_name,
        revision=s.embedding_model_revision,
        local_dir=target,
        # Skip ONNX/OpenVINO/TF variants; PyTorch safetensors is all we need.
        allow_patterns=[
            "*.json",
            "*.txt",
            "*.model",
            "*.safetensors",
            "1_Pooling/*",
            "sentencepiece*",
        ],
        ignore_patterns=["onnx/*", "openvino/*"],
    )
    print("Done. You can now work fully offline.")


if __name__ == "__main__":
    main()
