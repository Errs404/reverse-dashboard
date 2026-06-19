#!/usr/bin/env bash
set -euo pipefail

WANT_PM2=0
WANT_NGINX=0
if [ "$#" -eq 0 ]; then
  WANT_PM2=1
  WANT_NGINX=1
fi
for arg in "$@"; do
  case "$arg" in
    --pm2) WANT_PM2=1 ;;
    --nginx) WANT_NGINX=1 ;;
    --all) WANT_PM2=1; WANT_NGINX=1 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

if [ "$(id -u)" -ne 0 ]; then
  echo "Please run as root: sudo bash scripts/install-runtime-tools.sh --all" >&2
  exit 1
fi

have() { command -v "$1" >/dev/null 2>&1; }

install_debian_packages() {
  export DEBIAN_FRONTEND=noninteractive
  apt-get update
  apt-get install -y "$@"
}

install_rhel_packages() {
  if have dnf; then dnf install -y "$@"; else yum install -y "$@"; fi
}

install_pkg() {
  if have apt-get; then
    install_debian_packages "$@"
  elif have dnf || have yum; then
    install_rhel_packages "$@"
  else
    echo "Unsupported Linux package manager. Install manually: $*" >&2
    exit 3
  fi
}

if [ "$WANT_NGINX" -eq 1 ]; then
  if have nginx; then
    echo "nginx already installed: $(command -v nginx)"
  else
    echo "Installing nginx..."
    install_pkg nginx
  fi
  if have systemctl; then
    systemctl enable --now nginx || true
  fi
  nginx -t || true
fi

if [ "$WANT_PM2" -eq 1 ]; then
  if ! have node || ! have npm; then
    echo "Installing nodejs/npm..."
    install_pkg nodejs npm
  fi
  if have pm2; then
    echo "pm2 already installed: $(command -v pm2)"
  else
    echo "Installing pm2 globally..."
    npm install -g pm2
  fi
  pm2 -v || true
fi

echo "Runtime tool installation check complete."
