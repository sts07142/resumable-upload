"""Integration tests for FastAPI example."""

import os
import tempfile

import pytest

# Skip tests if FastAPI is not installed
pytest.importorskip("fastapi")
httpx = pytest.importorskip("httpx")

from fastapi import FastAPI, Request, Response  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from resumable_upload import SQLiteStorage, TusServer  # noqa: E402


@pytest.fixture
def temp_dir():
    """Create a temporary directory for uploads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def fastapi_app(temp_dir):
    """Create a FastAPI app with TUS server for testing."""
    app = FastAPI()

    db_path = os.path.join(temp_dir, "test_uploads.db")
    upload_dir = os.path.join(temp_dir, "uploads")
    storage = SQLiteStorage(db_path=db_path, upload_dir=upload_dir)
    tus_server = TusServer(storage=storage, base_path="/files")

    @app.options("/files")
    @app.post("/files")
    async def create_upload(request: Request):
        return await handle_tus_request(request, tus_server)

    @app.head("/files/{upload_id}")
    @app.patch("/files/{upload_id}")
    @app.delete("/files/{upload_id}")
    async def handle_upload(upload_id: str, request: Request):
        return await handle_tus_request(request, tus_server)

    async def handle_tus_request(request: Request, server: TusServer):
        path = request.url.path
        headers = dict(request.headers)
        body = await request.body()
        status, response_headers, response_body = server.handle_request(
            request.method, path, headers, body
        )
        return Response(content=response_body, status_code=status, headers=response_headers)

    return app


@pytest.fixture
def client(fastapi_app):
    """Create a test client."""
    return TestClient(fastapi_app)


def test_fastapi_options_request(client: TestClient):
    """Test OPTIONS request returns TUS headers."""
    response = client.options("/files")
    assert response.status_code == 204
    assert "tus-resumable" in response.headers
    assert response.headers["tus-resumable"] == "1.0.0"
    assert "tus-version" in response.headers
    assert "tus-extension" in response.headers


def test_fastapi_create_upload(client: TestClient):
    """Test creating an upload via POST."""
    response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "100",
            "Upload-Metadata": "filename dGVzdC50eHQ=",
        },
    )
    assert response.status_code == 201
    assert "location" in response.headers
    assert "/files/" in response.headers["location"]
    assert "tus-resumable" in response.headers


def test_fastapi_head_request(client: TestClient):
    """Test HEAD request returns upload offset."""
    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "100",
        },
    )
    upload_url = create_response.headers["location"]
    upload_id = upload_url.split("/")[-1]

    # Check offset
    response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert response.status_code == 200
    assert "upload-offset" in response.headers
    assert response.headers["upload-offset"] == "0"


def test_fastapi_patch_upload(client: TestClient):
    """Test uploading data via PATCH."""
    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "13",
        },
    )
    upload_url = create_response.headers["location"]
    upload_id = upload_url.split("/")[-1]

    # Upload data
    data = b"Hello, World!"
    response = client.patch(
        f"/files/{upload_id}",
        content=data,
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": str(len(data)),
        },
    )
    assert response.status_code == 204
    assert "upload-offset" in response.headers
    assert response.headers["upload-offset"] == "13"


def test_fastapi_delete_upload(client: TestClient):
    """Test deleting an upload via DELETE."""
    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "100",
        },
    )
    upload_url = create_response.headers["location"]
    upload_id = upload_url.split("/")[-1]

    # Delete upload
    response = client.delete(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert response.status_code == 204

    # Verify it's deleted
    response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert response.status_code == 404


def test_fastapi_complete_upload_flow(client: TestClient):
    """Test complete upload flow from creation to completion."""
    data = b"Test data for complete upload flow"
    upload_length = len(data)

    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(upload_length),
            "Upload-Metadata": "filename dGVzdC50eHQ=",
        },
    )
    assert create_response.status_code == 201
    upload_url = create_response.headers["location"]
    upload_id = upload_url.split("/")[-1]

    # Check initial offset
    head_response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert head_response.status_code == 200
    assert head_response.headers["upload-offset"] == "0"

    # Upload data
    patch_response = client.patch(
        f"/files/{upload_id}",
        content=data,
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": str(upload_length),
        },
    )
    assert patch_response.status_code == 204
    assert patch_response.headers["upload-offset"] == str(upload_length)

    # Verify upload is complete
    final_head_response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert final_head_response.status_code == 200
    assert final_head_response.headers["upload-offset"] == str(upload_length)


def test_fastapi_chunked_upload(client: TestClient):
    """Test uploading data in multiple chunks."""
    total_data = b"This is a test message uploaded in chunks"
    chunk1 = total_data[:20]
    chunk2 = total_data[20:]

    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(len(total_data)),
        },
    )
    upload_url = create_response.headers["location"]
    upload_id = upload_url.split("/")[-1]

    # Upload first chunk
    response1 = client.patch(
        f"/files/{upload_id}",
        content=chunk1,
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
        },
    )
    assert response1.status_code == 204
    assert response1.headers["upload-offset"] == str(len(chunk1))

    # Upload second chunk
    response2 = client.patch(
        f"/files/{upload_id}",
        content=chunk2,
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": str(len(chunk1)),
            "Content-Type": "application/offset+octet-stream",
        },
    )
    assert response2.status_code == 204
    assert response2.headers["upload-offset"] == str(len(total_data))
