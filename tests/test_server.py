"""Test suite for server module."""

import os
import shutil
import tempfile

import pytest

from resumable_upload.server import TusServer
from resumable_upload.storage import SQLiteStorage


class TestTusServer:
    """Tests for TusServer."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def storage(self, temp_dir):
        """Create a storage instance for tests."""
        db_path = os.path.join(temp_dir, "test.db")
        upload_dir = os.path.join(temp_dir, "uploads")
        return SQLiteStorage(db_path=db_path, upload_dir=upload_dir)

    @pytest.fixture
    def server(self, storage):
        """Create a server instance for tests."""
        return TusServer(storage=storage, base_path="/files")

    def test_handle_options(self, server):
        """Test OPTIONS request."""
        status, headers, body = server.handle_request("OPTIONS", "/files", {})

        assert status == 204
        assert headers["Tus-Resumable"] == "1.0.0"
        assert headers["Tus-Version"] == "1.0.0"
        assert "creation" in headers["Tus-Extension"]

    def test_handle_create(self, server):
        """Test POST request to create upload."""
        headers = {
            "tus-resumable": "1.0.0",
            "upload-length": "1024",
            "upload-metadata": "filename dGVzdC50eHQ=",  # base64("test.txt")
        }

        status, response_headers, body = server.handle_request("POST", "/files", headers)

        assert status == 201
        assert "Location" in response_headers
        assert response_headers["Upload-Offset"] == "0"

    def test_handle_create_without_length(self, server):
        """Test POST request without Upload-Length."""
        headers = {
            "tus-resumable": "1.0.0",
        }

        status, response_headers, body = server.handle_request("POST", "/files", headers)

        assert status == 400

    def test_handle_head(self, server, storage):
        """Test HEAD request to get upload info."""
        # Create upload
        upload_id = "test-upload"
        storage.create_upload(upload_id, 1024, {"filename": "test.txt"})

        headers = {"tus-resumable": "1.0.0"}

        status, response_headers, body = server.handle_request(
            "HEAD", f"/files/{upload_id}", headers
        )

        assert status == 200
        assert response_headers["Upload-Offset"] == "0"
        assert response_headers["Upload-Length"] == "1024"

    def test_handle_head_not_found(self, server):
        """Test HEAD request for non-existent upload."""
        headers = {"tus-resumable": "1.0.0"}

        status, response_headers, body = server.handle_request(
            "HEAD", "/files/nonexistent", headers
        )

        assert status == 404

    def test_handle_patch(self, server, storage):
        """Test PATCH request to upload data."""
        # Create upload
        upload_id = "test-upload"
        storage.create_upload(upload_id, 100, {"filename": "test.txt"})

        headers = {
            "tus-resumable": "1.0.0",
            "upload-offset": "0",
            "content-type": "application/offset+octet-stream",
        }

        data = b"Hello World!"

        status, response_headers, body = server.handle_request(
            "PATCH", f"/files/{upload_id}", headers, data
        )

        assert status == 204
        assert response_headers["Upload-Offset"] == str(len(data))

        # Verify data was written
        uploaded_data = storage.read_file(upload_id)
        assert uploaded_data.startswith(data)

    def test_handle_patch_offset_mismatch(self, server, storage):
        """Test PATCH request with offset mismatch."""
        upload_id = "test-upload"
        storage.create_upload(upload_id, 100, {})

        headers = {
            "tus-resumable": "1.0.0",
            "upload-offset": "50",  # Wrong offset
            "content-type": "application/offset+octet-stream",
        }

        status, response_headers, body = server.handle_request(
            "PATCH", f"/files/{upload_id}", headers, b"data"
        )

        assert status == 409

    def test_handle_patch_invalid_content_type(self, server, storage):
        """Test PATCH request with invalid content type."""
        upload_id = "test-upload"
        storage.create_upload(upload_id, 100, {})

        headers = {
            "tus-resumable": "1.0.0",
            "upload-offset": "0",
            "content-type": "text/plain",  # Wrong content type
        }

        status, response_headers, body = server.handle_request(
            "PATCH", f"/files/{upload_id}", headers, b"data"
        )

        assert status == 400

    def test_handle_delete(self, server, storage):
        """Test DELETE request to terminate upload."""
        upload_id = "test-upload"
        storage.create_upload(upload_id, 100, {})

        headers = {"tus-resumable": "1.0.0"}

        status, response_headers, body = server.handle_request(
            "DELETE", f"/files/{upload_id}", headers
        )

        assert status == 204
        assert storage.get_upload(upload_id) is None

    def test_handle_delete_not_found(self, server):
        """Test DELETE request for non-existent upload."""
        headers = {"tus-resumable": "1.0.0"}

        status, response_headers, body = server.handle_request(
            "DELETE", "/files/nonexistent", headers
        )

        assert status == 404

    def test_invalid_tus_version(self, server):
        """Test request with invalid TUS version."""
        headers = {"tus-resumable": "0.9.0"}

        status, response_headers, body = server.handle_request("POST", "/files", headers)

        assert status == 412

    def test_max_size_limit(self, storage):
        """Test upload size limit."""
        server = TusServer(storage=storage, max_size=1000)

        headers = {
            "tus-resumable": "1.0.0",
            "upload-length": "2000",
        }

        status, response_headers, body = server.handle_request("POST", "/files", headers)

        assert status == 413
