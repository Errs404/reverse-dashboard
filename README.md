# Reverse Dashboard

Reverse Dashboard adalah dashboard server berbasis Flask untuk monitoring, pengelolaan file, Docker, dan fitur administrasi host dengan struktur yang aman serta mudah dikembangkan.

## Fitur v2 alpha

- Flask app factory + blueprint modular.
- Setup owner pertama dan login session.
- Role/permission dasar: owner, admin, operator, readonly.
- Dashboard CPU/RAM/disk/network/process.
- File browser + text editor sederhana.
- Docker container list/action/logs.
- Settings JSON persist.
- Audit log.
- Dockerfile dan docker-compose yang lebih aman: port default 8080 dan host root read-only.

## Struktur

```text
reverse_dashboard/
  app.py                 # app factory + blueprint registration
  config.py              # config/env
  security.py            # decorators auth/permission
  blueprints/            # routes per fitur
  services/              # logic non-route
  templates/             # UI Jinja
  static/                # CSS/JS
wsgi.py                  # entrypoint dev/prod
requirements.txt
Dockerfile
docker-compose.yml
```

## Jalankan lokal

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python wsgi.py
```

Buka `http://localhost:5000`, lalu buat owner pertama.

## Jalankan Docker

```bash
docker compose up --build -d
```

Buka `http://SERVER_IP:8080`.

## Catatan keamanan

- Jangan pakai `SECRET_KEY=change-this-secret` untuk production.
- Compose default mount `/host/root` sebagai read-only.
- `ENABLE_HOST_CONTROL=0` default; fitur host-control destruktif belum diaktifkan.
- Semua API Docker/File/Settings diproteksi decorator permission.
- Password memakai `werkzeug.security.generate_password_hash`, bukan SHA-256 polos.

## Roadmap pengembangan aman

### Fase 0 - Guardrail sebelum fitur host-level

- Tambahkan test smoke untuk app factory, auth, permission, file root confinement, dan Docker action permission.
- Semua fitur destruktif wajib lewat permission decorator, audit log, dan confirmation flow yang spesifik.
- Default production harus aman: `SECRET_KEY` kuat, `FILES_READ_ONLY=1` untuk host mount read-only, dan `ENABLE_HOST_CONTROL=0`.
- API host-level baru wajib punya feature flag sendiri, bukan hanya bergantung pada role.

### Fase 1 - Core dashboard yang stabil

- Perkuat session timeout, user management, dan perubahan password.
- Lanjutkan hardening Files: root terbatas ke `HOST_ROOT`, read-only mode, dan validasi path.
- Lanjutkan hardening Docker: batasi operator ke restart, audit semua action, dan tampilkan error Docker yang aman.
- Tambahkan backup/restore manual untuk `data/security.json`, `settings.json`, dan `audit.log` sebelum pengembangan fitur besar.

### Fase 2 - Terminal dan host command terbatas

- Aktifkan hanya jika `ENABLE_HOST_CONTROL=1` dan role `owner`/`admin`.
- Mulai dari command allowlist, bukan shell bebas.
- Wajib ada preview command, konfirmasi ketik target, timeout proses, capture output, dan audit detail.
- Hindari menyimpan output yang berisi secret ke audit log.

### Fase 3 - Nginx/Websites

- Pisahkan model data website dari operasi sistem.
- Validasi config dengan dry-run sebelum reload service.
- Gunakan staging file + atomic replace untuk config yang dihasilkan.
- Audit create/update/delete/reload, termasuk nama site dan path config.

### Fase 4 - Backup dan mobile backup

- Implement backup read-only lebih dulu: list, download, dan verify checksum.
- Tambahkan job write/delete setelah ada retention policy, quota, dan konfirmasi destruktif.
- Buat restore sebagai flow terpisah dengan dry-run dan rollback plan.

### Fase 5 - LXD, VPN, Samba, dan app store

- Tambahkan per-modul feature flag: misalnya `ENABLE_LXD`, `ENABLE_VPN`, `ENABLE_SAMBA`.
- Jangan gabungkan banyak operasi host dalam satu endpoint generik.
- Setiap modul perlu permission granular, audit event khusus, dan health/status endpoint.
- Rilis bertahap per modul agar rollback mudah jika satu modul bermasalah.
