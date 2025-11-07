"""Test suite for client module."""

import os
import shutil
import tempfile
from http.server import HTTPServer
from threading import Thread

import pytest

from resumable_upload.client import TusClient
from resumable_upload.server import TusHTTPRequestHandler, TusServer
from resumable_upload.storage import SQLiteStorage


class TestTusClient:
    """Tests for TusClient."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir)

    @pytest.fixture
    def test_file(self, temp_dir):
        """Create a test file."""
        file_path = os.path.join(temp_dir, "test_file.txt")
        with open(file_path, "wb") as f:
            f.write(b"Hello World! " * 1000)
        return file_path

    @pytest.fixture
    def server(self, temp_dir):
        """Start a test server."""
        db_path = os.path.join(temp_dir, "test.db")
        upload_dir = os.path.join(temp_dir, "uploads")
        storage = SQLiteStorage(db_path=db_path, upload_dir=upload_dir)
        tus_server = TusServer(storage=storage, base_path="/files")

        # Create custom handler class
        class CustomHandler(TusHTTPRequestHandler):
            pass

        CustomHandler.tus_server = tus_server

        # Start server in a thread
        server = HTTPServer(("127.0.0.1", 0), CustomHandler)
        port = server.server_address[1]
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()

        yield f"http://127.0.0.1:{port}/files", storage

        server.shutdown()

    @pytest.fixture
    def client(self, server):
        """Create a client instance."""
        url, _ = server
        return TusClient(url, chunk_size=1024)

    def test_upload_file(self, client, test_file, server):
        """Test uploading a file."""
        url, storage = server

        # Track progress
        progress_calls = []

        def progress_callback(uploaded, total):
            progress_calls.append((uploaded, total))

        upload_url = client.upload_file(
            test_file,
            metadata={"filename": "test.txt"},
            progress_callback=progress_callback,
        )

        assert upload_url is not None
        assert upload_url.startswith(url)

        # Verify progress was tracked
        assert len(progress_calls) > 0
        assert progress_calls[-1][0] == progress_calls[-1][1]

        # Verify file was uploaded
        upload_id = upload_url.split("/")[-1]
        upload = storage.get_upload(upload_id)
        assert upload is not None
        assert upload["completed"] is True

    def test_upload_nonexistent_file(self, client):
        """Test uploading a non-existent file."""
        with pytest.raises(FileNotFoundError):
            client.upload_file("/nonexistent/file.txt")

    def test_resume_upload(self, client, test_file, server):
        """Test resuming an upload."""
        url, storage = server

        # Start upload
        file_size = os.path.getsize(test_file)

        # Create upload manually
        with open(test_file, "rb") as f:
            # Upload first chunk
            headers = {
                "Tus-Resumable": "1.0.0",
                "Upload-Length": str(file_size),
            }

            from urllib.request import Request, urlopen

            req = Request(url, headers=headers, method="POST")
            with urlopen(req) as response:
                location = response.headers.get("Location")
                # Handle relative URL
                if not location.startswith("http"):
                    from urllib.parse import urljoin

                    upload_url = urljoin(url, location)
                else:
                    upload_url = location

            # Upload partial data
            chunk = f.read(1024)
            headers = {
                "Tus-Resumable": "1.0.0",
                "Upload-Offset": "0",
                "Content-Type": "application/offset+octet-stream",
            }
            req = Request(upload_url, data=chunk, headers=headers, method="PATCH")
            with urlopen(req) as response:
                pass

        # Resume upload
        upload_url_resumed = client.resume_upload(test_file, upload_url)
        assert upload_url_resumed == upload_url

        # Verify completion
        upload_id = upload_url.split("/")[-1]
        upload = storage.get_upload(upload_id)
        assert upload["completed"] is True

    def test_delete_upload(self, client, test_file, server):
        """Test deleting an upload."""
        url, storage = server

        # Upload file
        upload_url = client.upload_file(test_file)

        # Delete upload
        client.delete_upload(upload_url)

        # Verify deletion
        upload_id = upload_url.split("/")[-1]
        upload = storage.get_upload(upload_id)
        assert upload is None

    def test_client_without_checksum(self, test_file, server):
        """Test client with checksum disabled."""
        url, storage = server
        client = TusClient(url, checksum=False)

        upload_url = client.upload_file(test_file)
        assert upload_url is not None

        upload_id = upload_url.split("/")[-1]
        upload = storage.get_upload(upload_id)
        assert upload["completed"] is True
