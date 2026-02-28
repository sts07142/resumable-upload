# Storage

## SQLiteStorage

SQLite + filesystem storage backend.

```python
from resumable_upload import SQLiteStorage
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `db_path` | str | `"uploads.db"` | SQLite database file path |
| `upload_dir` | str | `"uploads"` | Directory for uploaded file chunks |

### Concurrency

`write_chunk()` is safe under concurrent access:

- **In-process (threads)**: Per-upload `threading.Lock` ensures only one thread writes to a given upload at a time.
- **Cross-process (multi-worker)**: `fcntl.flock(LOCK_EX)` on the file provides POSIX advisory locking. Falls back gracefully on non-POSIX systems (e.g., Windows).

`update_offset_atomic()` uses `UPDATE ... WHERE offset = expected` — if another request already advanced the offset, it returns `False` and the server responds with `409`.

### Custom Storage Backends

Subclass `Storage` to implement a custom backend:

```python
from resumable_upload.storage import Storage

class MyStorage(Storage):
    def create_upload(self, upload_id, upload_length, metadata, expires_at=None): ...
    def get_upload(self, upload_id): ...
    def update_offset(self, upload_id, offset): ...
    def delete_upload(self, upload_id): ...
    def write_chunk(self, upload_id, offset, data): ...
    def read_file(self, upload_id): ...
    def get_file_path(self, upload_id): ...
    def get_expired_uploads(self): ...
    def cleanup_expired_uploads(self): ...
    # Optional override for true atomicity (default: non-atomic read-then-write):
    def update_offset_atomic(self, upload_id, expected_offset, new_offset) -> bool: ...
```

---

## FileURLStorage

JSON file-based URL storage for cross-session resumability.

```python
from resumable_upload import FileURLStorage
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `storage_path` | str | `".tus_urls.json"` | Path to the JSON storage file |

### Concurrency

- **In-process (threads)**: `threading.Lock` serializes all reads and writes.
- **Cross-process (multi-worker)**: `fcntl.flock(LOCK_SH/LOCK_EX)` provides shared/exclusive POSIX file locks on a companion `.lock` file. Falls back gracefully on non-POSIX systems.
- Writes use `os.replace()` (atomic rename) to prevent torn reads.

### Custom URL Storage Backends

```python
from resumable_upload.url_storage import URLStorage

class MyURLStorage(URLStorage):
    def get_url(self, fingerprint: str) -> str | None: ...
    def set_url(self, fingerprint: str, url: str) -> None: ...
    def remove_url(self, fingerprint: str) -> None: ...
```
