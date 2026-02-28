# Client

## TusClient

Main client class for uploading files via TUS protocol.

```python
from resumable_upload import TusClient
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | — | TUS server base URL |
| `chunk_size` | int \| float | `1_048_576` (1 MB) | Upload chunk size in bytes |
| `checksum` | bool | `True` | Enable SHA1 `Upload-Checksum` verification |
| `verify_tls_cert` | bool | `True` | Verify TLS certificates |
| `metadata_encoding` | str | `"utf-8"` | Encoding for metadata values |
| `store_url` | bool | `False` | Persist upload URLs for cross-session resume |
| `url_storage` | URLStorage | `None` | Custom URL storage backend |
| `fingerprinter` | Fingerprint | `None` | Custom fingerprint implementation |
| `headers` | dict | `{}` | Custom headers added to all requests |
| `max_retries` | int | `3` | Max retry attempts per chunk (0 = disabled) |
| `retry_delay` | float | `1.0` | Base delay between retries (exponential backoff, capped at 60s) |
| `timeout` | float | `30.0` | Per-request socket timeout in seconds |

### Methods

#### `upload_file`

```python
client.upload_file(
    file_path=None,
    file_stream=None,
    metadata={},
    progress_callback=None,
    stop_at=None,
) -> str
```

Upload a file. Returns the upload URL.

- `stop_at` (int): Stop upload at this byte offset (for partial uploads). Clamped to file size automatically.

#### `resume_upload`

```python
client.resume_upload(file_path=None, upload_url="", file_stream=None, progress_callback=None) -> str
```

Resume an interrupted upload from its current server offset.

#### `delete_upload`

```python
client.delete_upload(upload_url: str) -> None
```

#### `get_upload_info`

```python
client.get_upload_info(upload_url: str) -> dict
# Returns: {"offset": int, "length": int, "complete": bool, "metadata": dict}
```

#### `get_server_info`

```python
client.get_server_info() -> dict
# Returns: {"version": str, "extensions": list[str], "max_size": int | None}
```

#### `create_uploader`

```python
client.create_uploader(
    file_path=None, file_stream=None, upload_url=None,
    metadata={}, chunk_size=None,
) -> Uploader
```

Create an `Uploader` instance for fine-grained chunk-level control.

---

## Uploader

Low-level upload controller for chunk-by-chunk control.

```python
from resumable_upload.client.uploader import Uploader
```

Typically obtained via `TusClient.create_uploader()`.

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | — | Existing upload URL on the server |
| `file_path` | str | `None` | Path to file (required if no `file_stream`) |
| `file_stream` | IO | `None` | File-like object (alternative to `file_path`) |
| `chunk_size` | int | `1_048_576` | Chunk size in bytes |
| `checksum` | bool | `True` | Enable SHA1 checksum |
| `max_retries` | int | `0` | Retry attempts per chunk |
| `retry_delay` | float | `1.0` | Base retry delay in seconds |
| `timeout` | float | `30.0` | Per-request timeout in seconds |
| `stop_event` | threading.Event | `None` | When set, interrupts retry wait and raises `TusUploadFailed`. Useful for cancellation in threaded applications. |

### 409 Handling

When the server returns `409 Conflict` (offset mismatch), the uploader automatically:
1. Sends a HEAD request to retrieve the current server offset
2. Seeks to that offset in the local file
3. Retries the chunk from the correct position

### Methods

| Method | Description |
|--------|-------------|
| `upload()` | Upload entire remaining file |
| `upload_chunk()` | Upload one chunk; returns `True` if more remain |
| `close()` | Release file handle |
| `is_complete` | Property: `True` if offset ≥ file size |
| `stats` | Property: `UploadStats` snapshot |
