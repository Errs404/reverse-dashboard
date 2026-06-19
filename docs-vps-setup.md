# Reverse Dashboard VPS Setup

Target: Ubuntu/Debian VPS. Jalankan sebagai root atau user sudo.

## 1. Install dependency OS

```bash
apt update
apt install -y git python3 python3-venv python3-pip curl ca-certificates
```

Opsional runtime tools:

```bash
bash scripts/install-runtime-tools.sh --all
```

Ini akan install/check Nginx, Node/npm, dan PM2.

## 2. Clone repo

```bash
cd /opt
git clone https://github.com/Errs404/reverse-dashboard.git reverse-dashboard
cd /opt/reverse-dashboard
```

## 3. Python environment

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4. Environment production

```bash
cp .env.example .env
nano .env
```

Minimal ubah:

```env
SECRET_KEY=isi-dengan-random-panjang
REVERSE_DASHBOARD_DATA=/opt/reverse-dashboard/data
HOST_ROOT=/
FILES_READ_ONLY=1
ENABLE_TERMINAL=1
```

Generate secret:

```bash
python3 - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
```

## 5. Systemd service

Buat service:

```bash
cat >/etc/systemd/system/reverse-dashboard.service <<'EOF'
[Unit]
Description=Reverse Dashboard
After=network-online.target docker.service
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/reverse-dashboard
EnvironmentFile=/opt/reverse-dashboard/.env
ExecStart=/opt/reverse-dashboard/.venv/bin/python /opt/reverse-dashboard/wsgi.py
Restart=always
RestartSec=5
User=root
Group=root

[Install]
WantedBy=multi-user.target
EOF
```

Start:

```bash
systemctl daemon-reload
systemctl enable --now reverse-dashboard
systemctl status reverse-dashboard
journalctl -u reverse-dashboard -f
```

App default listen `0.0.0.0:5000` dari `wsgi.py`.

## 6. Nginx reverse proxy

Contoh domain `panel.example.com`:

```bash
cat >/etc/nginx/sites-available/reverse-dashboard <<'EOF'
server {
    listen 80;
    server_name panel.example.com;

    client_max_body_size 512M;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
EOF
ln -sf /etc/nginx/sites-available/reverse-dashboard /etc/nginx/sites-enabled/reverse-dashboard
nginx -t
systemctl reload nginx
```

HTTPS pakai certbot:

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d panel.example.com
```

## 7. Docker support

Kalau Docker belum ada:

```bash
apt install -y docker.io
systemctl enable --now docker
```

Cek:

```bash
docker ps
```

Karena service berjalan root, dashboard seharusnya bisa akses Docker socket host.

## 8. Google Drive backup via rclone

Install rclone:

```bash
curl https://rclone.org/install.sh | bash
rclone config
```

Buat remote misalnya `gdrive`, lalu set `.env`:

```env
ENABLE_GDRIVE_BACKUP=1
GDRIVE_REMOTE=gdrive:reverse-dashboard-backups
```

Restart:

```bash
systemctl restart reverse-dashboard
```

Test:

```bash
rclone ls gdrive:
```

## 9. First setup

Buka:

```text
http://SERVER_IP:5000
```

atau domain Nginx. Buat owner account pertama.

## 10. Update app

```bash
cd /opt/reverse-dashboard
git pull
. .venv/bin/activate
pip install -r requirements.txt
systemctl restart reverse-dashboard
```

## Security notes

- Dashboard berjalan root berarti terminal dan action host punya akses penuh.
- Gunakan password kuat.
- Pasang HTTPS.
- Batasi akses dengan firewall/VPN jika memungkinkan.
- Jangan commit `.env`, `data/`, atau backup archive.
