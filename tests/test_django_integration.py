"""Integration tests for Django example."""

import os
import tempfile

import pytest

# Skip tests if Django is not installed
pytest.importorskip("django")

from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory
from django.views.decorators.csrf import csrf_exempt

from resumable_upload import SQLiteStorage, TusServer


@pytest.fixture
def temp_dir():
    """Create a temporary directory for uploads."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def tus_view(temp_dir):
    """Create a Django view with TUS server for testing."""
    db_path = os.path.join(temp_dir, "test_uploads.db")
    upload_dir = os.path.join(temp_dir, "uploads")
    storage = SQLiteStorage(db_path=db_path, upload_dir=upload_dir)
    tus_server = TusServer(storage=storage, base_path="/files")

    @csrf_exempt
    def tus_upload_view(request, upload_id=None):
        path = request.path
        headers = {key: value for key, value in request.META.items() if key.startswith("HTTP_")}
        headers = {key[5:].replace("_", "-"): value for key, value in headers.items()}
        if request.META.get("CONTENT_TYPE"):
            headers["Content-Type"] = request.META["CONTENT_TYPE"]
        if request.META.get("CONTENT_LENGTH"):
            headers["Content-Length"] = request.META["CONTENT_LENGTH"]
        body = request.body
        status, response_headers, response_body = tus_server.handle_request(
            request.method, path, headers, body
        )
        response = HttpResponse(response_body, status=status)
        for key, value in response_headers.items():
            response[key] = value
        return response

    return tus_upload_view


@pytest.fixture
def request_factory():
    """Create a Django request factory."""
    if not settings.configured:
        settings.configure(
            DEBUG=True,
            SECRET_KEY="test-secret-key",
            ROOT_URLCONF="",
            ALLOWED_HOSTS=["*"],
            MIDDLEWARE=[],
        )
    return RequestFactory()


def test_django_options_request(tus_view, request_factory):
    """Test OPTIONS request returns TUS headers."""
    request = request_factory.options("/files")
    response = tus_view(request)
    assert response.status_code == 204
    assert "Tus-Resumable" in response
    assert response["Tus-Resumable"] == "1.0.0"
    assert "Tus-Version" in response
    assert "Tus-Extension" in response


def test_django_create_upload(tus_view, request_factory):
    """Test creating an upload via POST."""
    request = request_factory.post(
        "/files",
        HTTP_TUS_RESUMABLE="1.0.0",
        HTTP_UPLOAD_LENGTH="100",
        HTTP_UPLOAD_METADATA="filename dGVzdC50eHQ=",
    )
    response = tus_view(request)
    assert response.status_code == 201
    assert "Location" in response
    assert "/files/" in response["Location"]
    assert "Tus-Resumable" in response


def test_django_head_request(tus_view, request_factory):
    """Test HEAD request returns upload offset."""
    # Create upload
    create_request = request_factory.post(
        "/files", HTTP_TUS_RESUMABLE="1.0.0", HTTP_UPLOAD_LENGTH="100"
    )
    create_response = tus_view(create_request)
    upload_url = create_response["Location"]
    upload_id = upload_url.split("/")[-1]

    # Check offset
    head_request = request_factory.head(f"/files/{upload_id}", HTTP_TUS_RESUMABLE="1.0.0")
    response = tus_view(head_request, upload_id=upload_id)
    assert response.status_code == 200
    assert "Upload-Offset" in response
    assert response["Upload-Offset"] == "0"


def test_django_patch_upload(tus_view, request_factory):
    """Test uploading data via PATCH."""
    # Create upload
    create_request = request_factory.post(
        "/files", HTTP_TUS_RESUMABLE="1.0.0", HTTP_UPLOAD_LENGTH="13"
    )
    create_response = tus_view(create_request)
    upload_url = create_response["Location"]
    upload_id = upload_url.split("/")[-1]

    # Upload data
    data = b"Hello, World!"
    patch_request = request_factory.patch(
        f"/files/{upload_id}",
        data=data,
        content_type="application/offset+octet-stream",
        HTTP_TUS_RESUMABLE="1.0.0",
        HTTP_UPLOAD_OFFSET="0",
    )
    response = tus_view(patch_request, upload_id=upload_id)
    assert response.status_code == 204
    assert "Upload-Offset" in response
    assert response["Upload-Offset"] == "13"


def test_django_delete_upload(tus_view, request_factory):
    """Test deleting an upload via DELETE."""
    # Create upload
    create_request = request_factory.post(
        "/files", HTTP_TUS_RESUMABLE="1.0.0", HTTP_UPLOAD_LENGTH="100"
    )
    create_response = tus_view(create_request)
    upload_url = create_response["Location"]
    upload_id = upload_url.split("/")[-1]

    # Delete upload
    delete_request = request_factory.delete(f"/files/{upload_id}", HTTP_TUS_RESUMABLE="1.0.0")
    response = tus_view(delete_request, upload_id=upload_id)
    assert response.status_code == 204

    # Verify it's deleted
    head_request = request_factory.head(f"/files/{upload_id}", HTTP_TUS_RESUMABLE="1.0.0")
    response = tus_view(head_request, upload_id=upload_id)
    assert response.status_code == 404


def test_django_complete_upload_flow(tus_view, request_factory):
    """Test complete upload flow from creation to completion."""
    data = b"Test data for complete upload flow"
    upload_length = len(data)

    # Create upload
    create_request = request_factory.post(
        "/files",
        HTTP_TUS_RESUMABLE="1.0.0",
        HTTP_UPLOAD_LENGTH=str(upload_length),
        HTTP_UPLOAD_METADATA="filename dGVzdC50eHQ=",
    )
    create_response = tus_view(create_request)
    assert create_response.status_code == 201
    upload_url = create_response["Location"]
    upload_id = upload_url.split("/")[-1]

    # Check initial offset
    head_request = request_factory.head(f"/files/{upload_id}", HTTP_TUS_RESUMABLE="1.0.0")
    head_response = tus_view(head_request, upload_id=upload_id)
    assert head_response.status_code == 200
    assert head_response["Upload-Offset"] == "0"

    # Upload data
    patch_request = request_factory.patch(
        f"/files/{upload_id}",
        data=data,
        content_type="application/offset+octet-stream",
        HTTP_TUS_RESUMABLE="1.0.0",
        HTTP_UPLOAD_OFFSET="0",
    )
    patch_response = tus_view(patch_request, upload_id=upload_id)
    assert patch_response.status_code == 204
    assert patch_response["Upload-Offset"] == str(upload_length)

    # Verify upload is complete
    final_head_request = request_factory.head(f"/files/{upload_id}", HTTP_TUS_RESUMABLE="1.0.0")
    final_head_response = tus_view(final_head_request, upload_id=upload_id)
    assert final_head_response.status_code == 200
    assert final_head_response["Upload-Offset"] == str(upload_length)


def test_django_chunked_upload(tus_view, request_factory):
    """Test uploading data in multiple chunks."""
    total_data = b"This is a test message uploaded in chunks"
    chunk1 = total_data[:20]
    chunk2 = total_data[20:]

    # Create upload
    create_request = request_factory.post(
        "/files",
        HTTP_TUS_RESUMABLE="1.0.0",
        HTTP_UPLOAD_LENGTH=str(len(total_data)),
    )
    create_response = tus_view(create_request)
    upload_url = create_response["Location"]
    upload_id = upload_url.split("/")[-1]

    # Upload first chunk
    patch_request1 = request_factory.patch(
        f"/files/{upload_id}",
        data=chunk1,
        content_type="application/offset+octet-stream",
        HTTP_TUS_RESUMABLE="1.0.0",
        HTTP_UPLOAD_OFFSET="0",
    )
    response1 = tus_view(patch_request1, upload_id=upload_id)
    assert response1.status_code == 204
    assert response1["Upload-Offset"] == str(len(chunk1))

    # Upload second chunk
    patch_request2 = request_factory.patch(
        f"/files/{upload_id}",
        data=chunk2,
        content_type="application/offset+octet-stream",
        HTTP_TUS_RESUMABLE="1.0.0",
        HTTP_UPLOAD_OFFSET=str(len(chunk1)),
    )
    response2 = tus_view(patch_request2, upload_id=upload_id)
    assert response2.status_code == 204
    assert response2["Upload-Offset"] == str(len(total_data))
