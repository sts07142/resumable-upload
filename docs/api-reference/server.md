# Server

## TusServer

TUS 1.0.0 protocol server implementation.

```python
from resumable_upload import TusServer
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `storage` | Storage | `SQLiteStorage()` | Storage backend |
| `base_path` | str | `"/files"` | Base URL path for uploads |
| `max_size` | int | `0` | Max upload size in bytes (0 = unlimited) |
| `upload_expiry` | int | `None` | Upload TTL in seconds (None = no expiry) |
| `cors_allow_origins` | str | `None` | CORS `Access-Control-Allow-Origin` value |
| `cleanup_interval` | int | `60` | Min seconds between expired-upload cleanup runs |
| `request_timeout` | int | `30` | Socket read timeout in seconds for `TusHTTPRequestHandler`. Guards against Slowloris attacks. Set to `0` to disable. |

### Security Defaults

- **Metadata size limit**: `Upload-Metadata` headers larger than 4 KB return `400` (DoS protection)
- **Invalid base64 metadata**: Returns `400` instead of storing raw value
- **Negative `Content-Length`**: Returns `400`
- **Socket timeout**: 30s default via `TusHTTPRequestHandler.setup()` — prevents slow-read attacks
- **Concurrent writes**: Atomic `UPDATE ... WHERE offset = ?` prevents lost updates; returns `409` on conflict

### Methods

```python
server.handle_request(method, path, headers, body) -> (status, headers, body)
```

Framework-agnostic request handler. See [Web Frameworks](../web-frameworks/flask.md).

---

## TusHTTPRequestHandler

`BaseHTTPRequestHandler` subclass for use with Python's built-in `HTTPServer`.

```python
from resumable_upload import TusHTTPRequestHandler

class Handler(TusHTTPRequestHandler):
    pass

Handler.tus_server = tus_server
server = HTTPServer(("0.0.0.0", 8080), Handler)
```

The socket read timeout is automatically applied via `setup()` using `tus_server.request_timeout`.
