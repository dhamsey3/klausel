#!/usr/bin/env bash
# Only the Windows host may reach Klausel's services on this VM.
#
#   sudo scripts/vm/install-firewall.sh
#
# On the Hyper-V Default Switch the host is the VM's default gateway, but its IP
# changes when Windows reboots. So the rules are rebuilt from the current gateway at
# boot (after Docker) and whenever NetworkManager brings the link up or renews DHCP.
#
# - Docker ports (MinIO 9000/9001, Qdrant 6333/6334) are filtered in DOCKER-USER,
#   because Docker's own rules bypass ufw/INPUT.
# - Ollama (11434) runs on the host, so it is filtered in INPUT.
# Only NEW connections arriving on the external interface are affected; SSH (22),
# outgoing traffic and container-to-container traffic are untouched.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo." >&2; exit 1; }

install -m 0755 /dev/stdin /usr/local/sbin/klausel-firewall <<'RULES'
#!/usr/bin/env bash
set -euo pipefail
read -r gw iface < <(ip -4 route show default | awk '{print $3, $5; exit}')
[ -n "${gw:-}" ] && [ -n "${iface:-}" ] || { echo "klausel-firewall: no default route" >&2; exit 1; }

# Own chains, rebuilt from scratch on every run (idempotent).
for chain in KLAUSEL-DOCKER KLAUSEL-IN; do
  iptables -N "$chain" 2>/dev/null || iptables -F "$chain"
done
iptables -A KLAUSEL-DOCKER -i "$iface" -s "$gw" -j RETURN
iptables -A KLAUSEL-DOCKER -i "$iface" -p tcp -m multiport --dports 9000,9001,6333,6334 \
  -m conntrack --ctstate NEW -j DROP
iptables -A KLAUSEL-IN -i "$iface" -s "$gw" -j RETURN
iptables -A KLAUSEL-IN -i "$iface" -p tcp --dport 11434 -m conntrack --ctstate NEW -j DROP

iptables -N DOCKER-USER 2>/dev/null || true
iptables -C DOCKER-USER -j KLAUSEL-DOCKER 2>/dev/null || iptables -I DOCKER-USER 1 -j KLAUSEL-DOCKER
iptables -C INPUT -j KLAUSEL-IN 2>/dev/null || iptables -I INPUT 1 -j KLAUSEL-IN

# Ollama also listens on IPv6; nothing needs it there.
ip6tables -N KLAUSEL-IN6 2>/dev/null || ip6tables -F KLAUSEL-IN6
ip6tables -A KLAUSEL-IN6 -i "$iface" -p tcp --dport 11434 -j DROP
ip6tables -C INPUT -j KLAUSEL-IN6 2>/dev/null || ip6tables -I INPUT 1 -j KLAUSEL-IN6

echo "klausel-firewall: only $gw may reach 9000,9001,6333,6334,11434 on $iface"
RULES

cat > /etc/systemd/system/klausel-firewall.service <<'UNIT'
[Unit]
Description=Klausel: allow only the Hyper-V host to reach MinIO, Qdrant and Ollama
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStart=/usr/local/sbin/klausel-firewall

[Install]
WantedBy=multi-user.target
UNIT

# Re-apply when the link comes up or DHCP hands out a new address/gateway.
if [ -d /etc/NetworkManager/dispatcher.d ]; then
  install -m 0755 /dev/stdin /etc/NetworkManager/dispatcher.d/90-klausel-firewall <<'HOOK'
#!/bin/sh
case "$2" in up|dhcp4-change) systemctl restart klausel-firewall.service ;; esac
HOOK
fi

systemctl daemon-reload
systemctl enable klausel-firewall.service
systemctl restart klausel-firewall.service
systemctl --no-pager --lines=3 status klausel-firewall.service | tail -3
