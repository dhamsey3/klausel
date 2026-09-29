#!/usr/bin/env bash
# One-time VM setup (Ubuntu 22.04+): Docker + Compose v2 from Ubuntu's own packages,
# Docker networks moved off 172.17.x.x (Hyper-V Default Switch range), firewall.
#
#   sudo scripts/vm/install-docker.sh
set -euo pipefail
target_user="${SUDO_USER:-$USER}"

mkdir -p /etc/docker
cat > /etc/docker/daemon.json <<'JSON'
{ "bip": "10.200.0.1/24", "default-address-pools": [{ "base": "10.201.0.0/16", "size": 24 }] }
JSON

apt-get update
# The old Python "docker-compose" (v1) cannot read this project's compose file.
apt-get remove -y docker-compose 2>/dev/null || true
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2
systemctl enable docker
systemctl restart docker
usermod -aG docker "$target_user"

# Only if ufw is enabled: allow MinIO, Qdrant and Ollama from the Default Switch subnet.
if ufw status 2>/dev/null | grep -q "Status: active"; then
  ufw allow from 172.16.0.0/12 to any port 9000,9001,6333,11434 proto tcp
fi

docker --version
docker compose version
echo "Done. Log out and back in so '$target_user' can use docker without sudo."
