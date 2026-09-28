#!/bin/bash
set -euxo pipefail

# 1. OS updates and Docker
dnf update -y
dnf install -y docker
systemctl enable --now docker

# 2. Docker Compose plugin, pinned to a known version
COMPOSE_VERSION="v2.29.7"
mkdir -p /usr/local/lib/docker/cli-plugins
curl -fsSL "https://github.com/docker/compose/releases/download/${COMPOSE_VERSION}/docker-compose-linux-aarch64" \
  -o /usr/local/lib/docker/cli-plugins/docker-compose
chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

# 3. 2 GB swap, so a memory spike slows the machine down instead of killing a container
if [ ! -f /swapfile ]; then
  dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

# 4. Application directory, readable only by root and the docker group
mkdir -p /opt/gate
chmod 750 /opt/gate

echo "gate bootstrap complete"
