# Low-Level Uploader

`Uploader` gives you chunk-by-chunk control over the upload process.
Obtain one via `TusClient.create_uploader()` or instantiate directly.

## Chunk-by-Chunk Upload

```python
uploader = client.create_uploader("large_file.bin")

while uploader.upload_chunk():
    stats = uploader.stats
    print(f"Uploaded {stats.uploaded_bytes} / {stats.total_bytes} bytes")

uploader.close()
```

`upload_chunk()` returns `True` while there are more chunks to send, `False` when the upload is complete.

## Cancellation via `stop_event`

Pass a `threading.Event` to cancel an upload cleanly from another thread:

```python
import threading
from resumable_upload.client.uploader import Uploader

stop = threading.Event()

uploader = Uploader(
    url=upload_url,
    file_path="large_file.bin",
    stop_event=stop,
)

# From another thread:
stop.set()  # Interrupts the retry wait and raises TusUploadFailed("cancelled")
```

The event is checked during retry waits, so cancellation is responsive even on slow connections.

## 409 Conflict Auto-Recovery

When the server returns `409 Conflict` (offset mismatch), the uploader automatically:

1. Sends a HEAD request to fetch the current server offset
2. Seeks the local file to that offset
3. Retries the chunk from the correct position

This handles cases where a previous chunk was partially accepted by the server.
