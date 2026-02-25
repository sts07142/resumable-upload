# Examples

Runnable examples for the resumable-upload library.

## Quick Start

```bash
# 1. Start a server (choose one)
python examples/server_example.py        # built-in http.server  → :8080
python examples/server_example.py 9000   # custom port           → :9000
python examples/flask_example.py         # Flask                 → :5000
python examples/fastapi_example.py       # FastAPI               → :8000
python examples/django_example.py        # Django                → :8000

# 2. Create a test file
dd if=/dev/urandom of=/tmp/test.bin bs=1M count=20

# 3. Upload
python examples/client_example.py   http://localhost:8080/files /tmp/test.bin
python examples/resume_example.py   http://localhost:8080/files /tmp/test.bin
python examples/uploader_example.py http://localhost:8080/files /tmp/test.bin
```

---

## Server Examples

### `server_example.py` — Built-in HTTP server

Zero-dependency server using Python's `http.server`.

```bash
python examples/server_example.py           # → :8080
python examples/server_example.py 9000      # → :9000
```

Features: 100 MB limit · 1 h upload expiry · 5 min cleanup · CORS enabled

---

### `flask_example.py` — Flask

```bash
pip install flask
python examples/flask_example.py           # → :5000
python examples/flask_example.py 9000      # → :9000
```

---

### `fastapi_example.py` — FastAPI

```bash
pip install fastapi uvicorn
python examples/fastapi_example.py         # → :8000  (docs at /docs)
python examples/fastapi_example.py 9000    # → :9000
```

---

### `django_example.py` — Django

```bash
pip install django
python examples/django_example.py          # → :8000
python examples/django_example.py 9000     # → :9000
```

**Integrating into an existing Django project:**

```python
# views.py  — copy tus_upload_view from the example

# urls.py
from django.urls import path
from .views import tus_upload_view

urlpatterns = [
    path("files", tus_upload_view, name="tus-create"),
    path("files/<str:upload_id>", tus_upload_view, name="tus-upload"),
]
```

---

## Client Examples

### `client_example.py` — Basic upload

Uploads a file, inspects the result, and optionally deletes it.

```bash
python examples/client_example.py <server_url> <file_path> [headers_json]

# With authentication header
python examples/client_example.py http://localhost:8080/files file.bin \
    '{"Authorization": "Bearer my-token"}'
```

Features: progress bar · MB/s speed · `max_retries=3` · `timeout=30 s` · delete prompt

---

### `resume_example.py` — Cross-session resumability

Demonstrates uploads that survive process restarts.
On the **first run** the upload starts from byte 0.
On every **subsequent run** with the same file, the stored URL is reused and
the upload continues from the last confirmed offset.

```bash
python examples/resume_example.py <server_url> <file_path>

# Interrupt with Ctrl-C halfway, then run again to resume
python examples/resume_example.py http://localhost:8080/files large.bin
^C
python examples/resume_example.py http://localhost:8080/files large.bin
```

The mapping `{ fingerprint → upload_url }` is stored in `.tus_resume_urls.json`.

---

### `uploader_example.py` — Fine-grained control

Shows all `Uploader` use-cases: chunk-by-chunk, full upload, `is_complete`,
`stop_at`, and resume.

```bash
python examples/uploader_example.py <server_url> <file_path> [upload_url]

# Start fresh
python examples/uploader_example.py http://localhost:8080/files file.bin

# Resume at a known URL
python examples/uploader_example.py http://localhost:8080/files file.bin \
    http://localhost:8080/files/abc123
```

---

## Common Configuration

All server examples share the same configuration:

| Parameter | Value | Description |
|-----------|-------|-------------|
| `max_size` | 100 MB | Maximum upload size |
| `upload_expiry` | 3600 s | Uploads expire after 1 hour |
| `cleanup_interval` | 300 s | Expired uploads cleaned every 5 min |
| `cors_allow_origins` | `"*"` | CORS — restrict to specific origin in production |

Adjust these values directly in each example file.

---

## Production Notes

- **WSGI/ASGI**: use `gunicorn` (Flask/Django) or `uvicorn --workers N` (FastAPI)
- **CORS**: replace `"*"` with your frontend origin
- **Auth**: add an authentication middleware or check headers in the view
- **Storage**: `SQLiteStorage` is single-process; replace with a custom backend for multi-process deployments
- **HTTPS**: always terminate TLS in production; pass `verify_tls_cert=False` on the client only for self-signed certs in dev
