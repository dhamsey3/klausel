#!/usr/bin/env bash
# CPU-only Ollama for a VM without GPU, installed for the current user (no sudo).
# The official tarball is ~1.4 GB because of GPU libraries; they are skipped while
# streaming, so ~60 MB lands on disk. Runs as a systemd user service on 0.0.0.0:11434.
#
#   scripts/vm/install-ollama-cpu.sh [version] [model]
set -euo pipefail
version="${1:-0.34.4}"
model="${2:-qwen2.5:3b}"
dest="$HOME/.local/ollama"

command -v zstd >/dev/null || { echo "zstd is required: sudo apt install zstd" >&2; exit 1; }
mkdir -p "$dest"
wget -qO- "https://ollama.com/download/ollama-linux-amd64.tar.zst?version=${version}" \
  | zstd -d | tar -xf - -C "$dest" \
      --exclude="lib/ollama/cuda_*" --exclude="lib/ollama/rocm*" \
      --exclude="lib/ollama/vulkan*" --exclude="lib/ollama/mlx*"

mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ollama.service <<UNIT
[Unit]
Description=Ollama (CPU-only, user install) for Klausel
After=network-online.target

[Service]
ExecStart=%h/.local/ollama/bin/ollama serve
Environment=OLLAMA_HOST=0.0.0.0:11434
# Keep memory predictable on a small VM: one model, one request at a time.
Environment=OLLAMA_NUM_PARALLEL=1
Environment=OLLAMA_MAX_LOADED_MODELS=1
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now ollama
# Keep the service running without an open login session and start it at boot.
loginctl enable-linger "$USER" || echo "Run once: sudo loginctl enable-linger $USER"
sleep 2
"$dest/bin/ollama" pull "$model"
"$dest/bin/ollama" list
