# Examples

This directory contains example implementations of the resumable upload library with various web frameworks.

## Available Examples

### 1. Standard HTTP Server (`server_example.py`)

Basic implementation using Python's built-in `http.server` module.

**Usage:**
```bash
python examples/server_example.py
```

**Requirements:** None (uses standard library)

### 2. Flask Integration (`flask_example.py`)

Integration with Flask web framework.

**Usage:**
```bash
pip install flask
python examples/flask_example.py
```

**Features:**
- Simple Flask routes
- Request/response handling
- Logging enabled

### 3. FastAPI Integration (`fastapi_example.py`)

Modern async integration with FastAPI.

**Usage:**
```bash
pip install fastapi uvicorn
python examples/fastapi_example.py
```

**Features:**
- Async request handling
- Auto-generated API documentation at `/docs`
- Type hints and validation

### 4. Django Integration (`django_example.py`)

Integration with Django web framework.

**Usage:**
```bash
pip install django
python examples/django_example.py
```

**Features:**
- Django views and URL routing
- CSRF exemption for uploads
- Standalone runnable example

**For existing Django project:**
Add the view to your `views.py` and configure URLs as shown in the file comments.

### 5. Client Example (`client_example.py`)

Command-line client for uploading files.

**Usage:**
```bash
python examples/client_example.py http://localhost:8080/files /path/to/file.bin
```

## Common Features

All server examples include:
- TUS protocol v1.0.0 support
- SQLite storage backend
- 100MB upload size limit
- Comprehensive logging
- Same API endpoints:
  - `POST /files` - Create upload
  - `HEAD /files/{id}` - Get upload status
  - `PATCH /files/{id}` - Upload data
  - `DELETE /files/{id}` - Delete upload

## Testing Examples

### Start a Server
```bash
# Choose one:
python examples/server_example.py      # Standard HTTP (port 8080)
python examples/flask_example.py       # Flask (port 5000)
python examples/fastapi_example.py     # FastAPI (port 8000)
python examples/django_example.py      # Django (port 8000)
```

### Upload a File
```bash
# Create a test file
dd if=/dev/urandom of=test.bin bs=1M count=10

# Upload using basic client
python examples/client_example.py http://localhost:8080/files test.bin

# Upload using advanced client with retries
python examples/advanced_client_example.py http://localhost:8080/files test.bin 1
```

## Logging

All examples include logging configured at INFO level. You can adjust the logging level in each example:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change to DEBUG for more details
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
```

## Production Deployment

For production use:

1. **Use a production WSGI/ASGI server:**
   - Flask: `gunicorn` or `uwsgi`
   - FastAPI: `uvicorn` with `--workers`
   - Django: `gunicorn` or `uwsgi`

2. **Configure proper storage:**
   - Use a dedicated directory with appropriate permissions
   - Consider using cloud storage for scalability
   - Implement cleanup for expired uploads

3. **Security considerations:**
   - Add authentication/authorization
   - Validate file types and sizes
   - Use HTTPS
   - Implement rate limiting

4. **Monitoring:**
   - Configure proper logging
   - Monitor disk usage
   - Track upload metrics
