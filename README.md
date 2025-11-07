# Resumable Upload

[![Python Version](https://img.shields.io/pypi/pyversions/resumable-upload.svg)](https://pypi.org/project/resumable-upload/)
[![PyPI Version](https://img.shields.io/pypi/v/resumable-upload.svg)](https://pypi.org/project/resumable-upload/)
[![License](https://img.shields.io/pypi/l/resumable-upload.svg)](https://github.com/sts07142/resumable-upload/blob/main/LICENSE)

**English** | [한국어](README.ko.md)

A Python implementation of the [TUS resumable upload protocol](https://tus.io/) v1.0.0 for server and client, with zero runtime dependencies.

## ✨ Features

- 🚀 **Zero Dependencies**: Built using Python standard library only (no external dependencies for core functionality)
- 📦 **Server & Client**: Complete implementation of both sides
- 🔄 **Resume Capability**: Automatically resume interrupted uploads
- ✅ **Data Integrity**: Optional SHA1 checksum verification
- 🔁 **Retry Logic**: Built-in automatic retry with exponential backoff
- 📊 **Progress Tracking**: Detailed upload progress callbacks with stats
- 🌐 **Web Framework Support**: Integration examples for Flask, FastAPI, and Django
- 🐍 **Python 3.9+**: Supports Python 3.9 through 3.14
- 🏪 **Storage Backend**: SQLite-based storage (extensible to other backends)
- 🔐 **TLS Support**: Certificate verification control and mTLS authentication
- 📝 **URL Storage**: Persist upload URLs across sessions
- 🎯 **TUS Protocol Compliant**: Implements TUS v1.0.0 core protocol with creation, termination, and checksum extensions

## 📦 Installation

### Using uv (Recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install the package
uv pip install resumable-upload
```

### Using pip

```bash
pip install resumable-upload
```

## 🚀 Quick Start

### Basic Server

```python
from http.server import HTTPServer
from resumable_upload import TusServer, TusHTTPRequestHandler, SQLiteStorage

# Create storage backend
storage = SQLiteStorage(db_path="uploads.db", upload_dir="uploads")

# Create TUS server
tus_server = TusServer(storage=storage, base_path="/files")

# Create HTTP handler
class Handler(TusHTTPRequestHandler):
    pass

Handler.tus_server = tus_server

# Start server
server = HTTPServer(("0.0.0.0", 8080), Handler)
print("Server running on http://localhost:8080")
server.serve_forever()
```

### Basic Client

```python
from resumable_upload import TusClient

# Create client
client = TusClient("http://localhost:8080/files")

# Upload file with progress callback
def progress(uploaded, total):
    print(f"Progress: {uploaded}/{total} bytes ({uploaded/total*100:.1f}%)")

upload_url = client.upload_file(
    "large_file.bin",
    metadata={"filename": "large_file.bin"},
    progress_callback=progress
)

print(f"Upload complete: {upload_url}")
```

## 🔧 Advanced Usage

### Client with Automatic Retry

```python
from resumable_upload import TusClientWithRetry

# Create client with retry capability
client = TusClientWithRetry(
    "http://localhost:8080/files",
    chunk_size=1.5*1024*1024,  # 1.5MB chunks (float is allowed)
    max_retries=3,         # Retry up to 3 times
    retry_delay=1.0,       # Initial delay between retries
    checksum=True          # Enable checksum verification
)

# Upload with detailed progress tracking
def progress_callback(stats):
    print(f"Progress: {stats.progress_percent:.1f}% | "
          f"Speed: {stats.upload_speed/1024/1024:.2f} MB/s | "
          f"ETA: {stats.eta_seconds:.0f}s | "
          f"Chunks: {stats.chunks_completed}/{stats.total_chunks} | "
          f"Retried: {stats.chunks_retried}")

upload_url = client.upload_file(
    "large_file.bin",
    metadata={"filename": "large_file.bin"},
    progress_callback=progress_callback
)
```

### Resume Interrupted Uploads

```python
# Resume an interrupted upload
upload_url = client.resume_upload("large_file.bin", upload_url)
```

### Cross-Session Resumability

```python
from resumable_upload import TusClient, FileURLStorage

# Enable URL storage for resumability across sessions
storage = FileURLStorage(".tus_urls.json")
client = TusClient(
    "http://localhost:8080/files",
    store_url=True,
    url_storage=storage
)

# Upload will automatically resume if interrupted and restarted
upload_url = client.upload_file("large_file.bin")
```

### Using File Streams

```python
# Upload from a file stream instead of a path
with open("file.bin", "rb") as fs:
    client = TusClient("http://localhost:8080/files")
    upload_url = client.upload_file(
        file_stream=fs,
        metadata={"filename": "file.bin"}
    )
```

### Exception Handling

```python
from resumable_upload import TusClient
from resumable_upload.exceptions import TusCommunicationError, TusUploadFailed

client = TusClient("http://localhost:8080/files")

try:
    upload_url = client.upload_file("file.bin")
except TusCommunicationError as e:
    print(f"Communication error: {e.message}, status: {e.status_code}")
except TusUploadFailed as e:
    print(f"Upload failed: {e.message}")
```

## 🌐 Web Framework Integration

### Flask

```python
from flask import Flask, request, make_response
from resumable_upload import TusServer, SQLiteStorage

app = Flask(__name__)
tus_server = TusServer(storage=SQLiteStorage())

@app.route('/files', methods=['OPTIONS', 'POST'])
@app.route('/files/<upload_id>', methods=['HEAD', 'PATCH', 'DELETE'])
def handle_upload(upload_id=None):
    status, headers, body = tus_server.handle_request(
        request.method, request.path, dict(request.headers), request.get_data()
    )
    response = make_response(body, status)
    for key, value in headers.items():
        response.headers[key] = value
    return response
```

### FastAPI

```python
from fastapi import FastAPI, Request, Response
from resumable_upload import TusServer, SQLiteStorage

app = FastAPI()
tus_server = TusServer(storage=SQLiteStorage())

@app.post("/files")
@app.head("/files/{upload_id}")
@app.patch("/files/{upload_id}")
@app.delete("/files/{upload_id}")
async def handle_upload(request: Request):
    body = await request.body()
    status, headers, response_body = tus_server.handle_request(
        request.method, request.url.path, dict(request.headers), body
    )
    return Response(content=response_body, status_code=status, headers=headers)
```

### Django

```python
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from resumable_upload import TusServer, SQLiteStorage

tus_server = TusServer(storage=SQLiteStorage())

@csrf_exempt
def tus_upload_view(request, upload_id=None):
    headers = {key[5:].replace('_', '-'): value
               for key, value in request.META.items() if key.startswith('HTTP_')}
    status, response_headers, response_body = tus_server.handle_request(
        request.method, request.path, headers, request.body
    )
    response = HttpResponse(response_body, status=status)
    for key, value in response_headers.items():
        response[key] = value
    return response
```

## 📚 API Reference

### TusClient

Main client class for uploading files.

**Parameters:**

- `url` (str): TUS server base URL
- `chunk_size` (int): Size of each upload chunk in bytes (default: 1MB)
- `checksum` (bool): Enable SHA1 checksum verification (default: False)
- `store_url` (bool): Store upload URLs for resumability (default: False)
- `url_storage` (URLStorage): URL storage backend (default: FileURLStorage)
- `verify_tls_cert` (bool): Verify TLS certificates (default: True)
- `metadata_encoding` (str): Metadata encoding (default: "utf-8")

**Methods:**

- `upload_file(file_path=None, file_stream=None, metadata={}, progress_callback=None)`: Upload a file
- `resume_upload(file_path, upload_url, progress_callback=None)`: Resume an interrupted upload
- `delete_upload(upload_url)`: Delete an upload
- `get_offset(upload_url)`: Get current upload offset

### TusClientWithRetry

Enhanced client with automatic retry capability (inherits from TusClient).

**Additional Parameters:**

- `max_retries` (int): Maximum number of retry attempts (default: 3)
- `retry_delay` (float): Initial delay between retries in seconds (default: 1.0)
- `max_retry_delay` (float): Maximum delay between retries in seconds (default: 60.0)

### TusServer

Server implementation of TUS protocol.

**Parameters:**

- `storage` (Storage): Storage backend for managing uploads
- `base_path` (str): Base path for TUS endpoints (default: "/files")
- `max_size` (int): Maximum upload size in bytes (default: None)

**Methods:**

- `handle_request(method, path, headers, body)`: Handle TUS protocol requests

### SQLiteStorage

SQLite-based storage backend.

**Parameters:**

- `db_path` (str): Path to SQLite database file (default: "uploads.db")
- `upload_dir` (str): Directory for storing upload files (default: "uploads")

## 🔍 TUS Protocol Compliance

This library implements TUS protocol version 1.0.0 with the following extensions:

- ✅ **Core Protocol**: Basic upload functionality (POST, HEAD, PATCH)
- ✅ **Creation**: Upload creation via POST
- ✅ **Termination**: Upload deletion via DELETE
- ✅ **Checksum**: SHA1 checksum verification

### Sequential Upload Requirement

**Important:** The TUS protocol requires chunks to be uploaded **sequentially**, not in parallel.

**Why Sequential?**

1. **Offset Validation**: Each chunk must be uploaded at the correct byte offset
2. **Data Integrity**: Prevents data corruption from race conditions
3. **Resume Capability**: Makes tracking received bytes straightforward and reliable
4. **Protocol Compliance**: TUS specification requires `Upload-Offset` to match current position

```python
# ❌ Parallel uploads cause conflicts:
# Chunk 1 at offset 0    → OK
# Chunk 3 at offset 2048 → FAIL (409: expected offset 1024)
# Chunk 2 at offset 1024 → FAIL (409: offset mismatch)

# ✅ Sequential uploads work correctly:
# Chunk 1 at offset 0    → OK (offset now 1024)
# Chunk 2 at offset 1024 → OK (offset now 2048)
# Chunk 3 at offset 2048 → OK (offset now 3072)
```

## 🧪 Testing

### Using uv (Recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install all dependencies (dev and test)
make install

# Run minimal tests (excluding web frameworks)
make test-minimal

# Run all tests (including web frameworks)
make test

# Or use Makefile for convenience
make lint              # Run linting
make format            # Format code
make test-minimal      # Run minimal tests
make test              # Run all tests
make test-all-versions # Test on all Python versions (3.9-3.14) - requires tox
make ci                # Run full CI checks (lint + format + test)
```

## 📖 Documentation

- **English**: [README.md](README.md)
- **한국어 (Korean)**: [README.ko.md](README.ko.md)
- **TUS Protocol Compliance**: [TUS_COMPLIANCE.md](TUS_COMPLIANCE.md)

## 🤝 Contributing

Contributions are welcome! Please check out the [Contributing Guide](.github/CONTRIBUTING.md) for guidelines.

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

This library is inspired by the official [TUS Python client](https://github.com/tus/tus-py-client) and implements the [TUS resumable upload protocol](https://tus.io/).

## 📞 Support

- 📫 Issues: [GitHub Issues](https://github.com/sts07142/resumable-upload/issues)
- 📖 Documentation: [GitHub README](https://github.com/sts07142/resumable-upload#readme)
- 🌟 Star us on GitHub!
