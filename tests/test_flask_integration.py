"""Integration tests for Flask example."""

import os
import tempfile

import pytest

# Skip tests if Flask is not installed
pytest.importorskip("flask")

from flask import Flask
from flask.testing import FlaskClient

from resumable_upload import SQLiteStorage, TusServer


@pytest.fixture
def temp_dir():
    """Create a temporary directory for uploads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def flask_app(temp_dir):
    """Create a Flask app with TUS server for testing."""
    app = Flask(__name__)
    app.config["TESTING"] = True

    db_path = os.path.join(temp_dir, "test_uploads.db")
    upload_dir = os.path.join(temp_dir, "uploads")
    storage = SQLiteStorage(db_path=db_path, upload_dir=upload_dir)
    tus_server = TusServer(storage=storage, base_path="/files")

    @app.route("/files", methods=["OPTIONS", "POST"])
    @app.route("/files/<upload_id>", methods=["HEAD", "PATCH", "DELETE"])
    def handle_upload(upload_id=None):
        from flask import make_response, request

        status, headers, body = tus_server.handle_request(
            request.method, request.path, dict(request.headers), request.get_data()
        )
        response = make_response(body, status)
        for key, value in headers.items():
            response.headers[key] = value
        return response

    return app


@pytest.fixture
def client(flask_app):
    """Create a test client."""
    return flask_app.test_client()


def test_flask_options_request(client: FlaskClient):
    """Test OPTIONS request returns TUS headers."""
    response = client.options("/files")
    assert response.status_code == 204
    assert "Tus-Resumable" in response.headers
    assert response.headers["Tus-Resumable"] == "1.0.0"
    assert "Tus-Version" in response.headers
    assert "Tus-Extension" in response.headers


def test_flask_create_upload(client: FlaskClient):
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
    assert "Location" in response.headers
    assert "/files/" in response.headers["Location"]
    assert "Tus-Resumable" in response.headers


def test_flask_head_request(client: FlaskClient):
    """Test HEAD request returns upload offset."""
    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "100",
        },
    )
    upload_url = create_response.headers["Location"]
    upload_id = upload_url.split("/")[-1]

    # Check offset
    response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert response.status_code == 200
    assert "Upload-Offset" in response.headers
    assert response.headers["Upload-Offset"] == "0"


def test_flask_patch_upload(client: FlaskClient):
    """Test uploading data via PATCH."""
    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "13",
        },
    )
    upload_url = create_response.headers["Location"]
    upload_id = upload_url.split("/")[-1]

    # Upload data
    data = b"Hello, World!"
    response = client.patch(
        f"/files/{upload_id}",
        data=data,
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": str(len(data)),
        },
    )
    assert response.status_code == 204
    assert "Upload-Offset" in response.headers
    assert response.headers["Upload-Offset"] == "13"


def test_flask_delete_upload(client: FlaskClient):
    """Test deleting an upload via DELETE."""
    # Create upload
    create_response = client.post(
        "/files",
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Length": "100",
        },
    )
    upload_url = create_response.headers["Location"]
    upload_id = upload_url.split("/")[-1]

    # Delete upload
    response = client.delete(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert response.status_code == 204

    # Verify it's deleted
    response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert response.status_code == 404


def test_flask_complete_upload_flow(client: FlaskClient):
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
    upload_url = create_response.headers["Location"]
    upload_id = upload_url.split("/")[-1]

    # Check initial offset
    head_response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert head_response.status_code == 200
    assert head_response.headers["Upload-Offset"] == "0"

    # Upload data
    patch_response = client.patch(
        f"/files/{upload_id}",
        data=data,
        headers={
            "Tus-Resumable": "1.0.0",
            "Upload-Offset": "0",
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": str(upload_length),
        },
    )
    assert patch_response.status_code == 204
    assert patch_response.headers["Upload-Offset"] == str(upload_length)

    # Verify upload is complete
    final_head_response = client.head(f"/files/{upload_id}", headers={"Tus-Resumable": "1.0.0"})
    assert final_head_response.status_code == 200
    assert final_head_response.headers["Upload-Offset"] == str(upload_length)
