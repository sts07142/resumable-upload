"""Test suite for Uploader class."""

import os
import shutil
import tempfile
from http.server import HTTPServer
from threading import Thread

import pytest

from resumable_upload.client import TusClient, Uploader
from resumable_upload.server import TusHTTPRequestHandler, TusServer
from resumable_upload.storage import SQLiteStorage


class TestUploader:
    """Tests for Uploader class."""

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
            f.write(b"Hello World! " * 1000)  # ~13KB file
        return file_path

    @pytest.fixture
    def server(self, temp_dir):
        """Start a test server."""
        db_path = os.path.join(temp_dir, "test.db")
        upload_dir = os.path.join(temp_dir, "uploads")
        storage = SQLiteStorage(db_path=db_path, upload_dir=upload_dir)
        tus_server = TusServer(storage=storage, base_path="/files")

        class CustomHandler(TusHTTPRequestHandler):
            pass

        CustomHandler.tus_server = tus_server

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

    def test_uploader_init_with_file_path(self, test_file, server):
        """Test Uploader initialization with file path."""
        url, storage = server

        # Create upload first
        client = TusClient(url)
        upload_url = client.upload_file(test_file)

        # Create uploader
        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024)

        assert uploader.url == upload_url
        assert uploader.file_path == test_file
        assert uploader.file_size == os.path.getsize(test_file)
        assert uploader.chunk_size == 1024
        assert uploader.offset >= 0

        uploader.close()

    def test_uploader_init_with_file_stream(self, test_file, server):
        """Test Uploader initialization with file stream."""
        url, storage = server

        # Create upload first
        client = TusClient(url)
        upload_url = client.upload_file(test_file)

        # Create uploader with file stream
        with open(test_file, "rb") as f:
            uploader = Uploader(url=upload_url, file_stream=f, chunk_size=1024)

            assert uploader.url == upload_url
            assert uploader.file_stream == f
            assert uploader.file_size == os.path.getsize(test_file)
            assert not uploader._owns_file

            uploader.close()

    def test_uploader_init_missing_file(self, server):
        """Test Uploader initialization with non-existent file."""
        url, storage = server

        with pytest.raises(FileNotFoundError):
            Uploader(url=f"{url}/nonexistent", file_path="/nonexistent/file.txt")

    def test_uploader_init_no_file(self, server):
        """Test Uploader initialization without file path or stream."""
        url, storage = server

        with pytest.raises(ValueError, match="Either file_path or file_stream"):
            Uploader(url=f"{url}/test")

    def test_uploader_context_manager(self, test_file, server):
        """Test Uploader as context manager."""
        url, storage = server

        client = TusClient(url)
        upload_url = client.upload_file(test_file)

        # Use as context manager
        with Uploader(url=upload_url, file_path=test_file) as uploader:
            assert uploader.url == upload_url
            # File should be closed automatically

    def test_upload_chunk(self, test_file, server):
        """Test uploading a single chunk."""
        url, storage = server

        # Create upload
        client = TusClient(url)  # noqa: F841
        file_size = os.path.getsize(test_file)

        from urllib.parse import urljoin
        from urllib.request import Request, urlopen

        headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(file_size),
        }
        req = Request(url, headers=headers, method="POST")
        with urlopen(req) as response:
            location = response.headers.get("Location")
            upload_url = urljoin(url, location) if not location.startswith("http") else location

        # Create uploader
        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024)

        # Upload single chunk
        has_more = uploader.upload_chunk()

        assert uploader.offset == 1024
        assert has_more is True  # More chunks remain

        # Upload another chunk
        has_more = uploader.upload_chunk()

        assert uploader.offset == 2048
        assert has_more is True

        uploader.close()

    def test_upload_chunk_complete(self, test_file, server):
        """Test uploading chunks until complete."""
        url, storage = server

        client = TusClient(url)
        upload_url = client.upload_file(test_file)

        # Create uploader (upload is already complete)
        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024)

        # Try to upload chunk (should return False)
        has_more = uploader.upload_chunk()

        assert has_more is False
        assert uploader.is_complete is True

        uploader.close()

    def test_upload_all(self, test_file, server):
        """Test uploading entire file."""
        url, storage = server

        # Create upload
        client = TusClient(url)  # noqa: F841
        file_size = os.path.getsize(test_file)

        from urllib.parse import urljoin
        from urllib.request import Request, urlopen

        headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(file_size),
        }
        req = Request(url, headers=headers, method="POST")
        with urlopen(req) as response:
            location = response.headers.get("Location")
            upload_url = urljoin(url, location) if not location.startswith("http") else location

        # Create uploader
        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024)

        # Track progress
        progress_calls = []

        def progress_callback(stats):
            progress_calls.append((stats.uploaded_bytes, stats.total_bytes))

        # Upload all
        result_url = uploader.upload(progress_callback=progress_callback)

        assert result_url == upload_url
        assert uploader.is_complete is True
        assert len(progress_calls) > 0
        assert progress_calls[-1][0] == progress_calls[-1][1]

        uploader.close()

    def test_upload_with_stop_at(self, test_file, server):
        """Test uploading with stop_at parameter."""
        url, storage = server

        # Create upload
        client = TusClient(url)  # noqa: F841
        file_size = os.path.getsize(test_file)

        from urllib.parse import urljoin
        from urllib.request import Request, urlopen

        headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(file_size),
        }
        req = Request(url, headers=headers, method="POST")
        with urlopen(req) as response:
            location = response.headers.get("Location")
            upload_url = urljoin(url, location) if not location.startswith("http") else location

        # Create uploader
        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024)

        # Upload with stop_at
        stop_at = 2048
        uploader.upload(stop_at=stop_at)

        assert uploader.offset == stop_at
        assert uploader.is_complete is False

        uploader.close()

    def test_uploader_progress(self, test_file, server):
        """Test uploader progress property."""
        url, storage = server

        client = TusClient(url)
        upload_url = client.upload_file(test_file)

        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024)

        # Check progress
        stats = uploader.stats
        assert stats.uploaded_bytes == stats.total_bytes  # Already complete
        assert stats.total_bytes == os.path.getsize(test_file)

        uploader.close()

    def test_uploader_is_complete(self, test_file, server):
        """Test uploader is_complete property."""
        url, storage = server

        # Create incomplete upload
        client = TusClient(url)  # noqa: F841
        file_size = os.path.getsize(test_file)

        from urllib.parse import urljoin
        from urllib.request import Request, urlopen

        headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(file_size),
        }
        req = Request(url, headers=headers, method="POST")
        with urlopen(req) as response:
            location = response.headers.get("Location")
            upload_url = urljoin(url, location) if not location.startswith("http") else location

        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024)

        assert uploader.is_complete is False

        # Upload all
        uploader.upload()

        assert uploader.is_complete is True

        uploader.close()

    def test_uploader_with_custom_headers(self, test_file, server):
        """Test uploader with custom headers."""
        url, storage = server

        client = TusClient(url)
        upload_url = client.upload_file(test_file)

        uploader = Uploader(
            url=upload_url,
            file_path=test_file,
            chunk_size=1024,
            headers={"Authorization": "Bearer token", "X-Custom": "value"},
        )

        assert uploader.headers == {"Authorization": "Bearer token", "X-Custom": "value"}

        uploader.close()

    def test_uploader_without_checksum(self, test_file, server):
        """Test uploader with checksum disabled."""
        url, storage = server

        client = TusClient(url)  # noqa: F841
        file_size = os.path.getsize(test_file)

        from urllib.parse import urljoin
        from urllib.request import Request, urlopen

        headers = {
            "Tus-Resumable": "1.0.0",
            "Upload-Length": str(file_size),
        }
        req = Request(url, headers=headers, method="POST")
        with urlopen(req) as response:
            location = response.headers.get("Location")
            upload_url = urljoin(url, location) if not location.startswith("http") else location

        uploader = Uploader(url=upload_url, file_path=test_file, chunk_size=1024, checksum=False)

        assert uploader.checksum is False

        # Upload should work without checksum
        uploader.upload_chunk()

        uploader.close()

    def test_uploader_invalid_chunk_size(self, test_file, server):
        """Test uploader with invalid chunk size."""
        url, storage = server

        client = TusClient(url)
        upload_url = client.upload_file(test_file)

        with pytest.raises(ValueError, match="chunk_size must be at least 1"):
            Uploader(url=upload_url, file_path=test_file, chunk_size=0)

        with pytest.raises(ValueError, match="chunk_size must be at least 1"):
            Uploader(url=upload_url, file_path=test_file, chunk_size=-1)
