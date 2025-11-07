"""Tests for retry client with robust error handling."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from resumable_upload import TusClientWithRetry, UploadStats


class TestUploadStats:
    """Test UploadStats dataclass."""

    def test_init(self):
        """Test UploadStats initialization."""
        stats = UploadStats(total_bytes=1000)
        assert stats.total_bytes == 1000
        assert stats.uploaded_bytes == 0
        assert stats.chunks_completed == 0
        assert stats.chunks_failed == 0
        assert stats.chunks_retried == 0
        assert stats.start_time > 0

    def test_elapsed_time(self):
        """Test elapsed time calculation."""
        stats = UploadStats(total_bytes=1000)
        import time

        time.sleep(0.1)
        assert stats.elapsed_time >= 0.1

    def test_upload_speed(self):
        """Test upload speed calculation."""
        stats = UploadStats(total_bytes=1000)
        stats.uploaded_bytes = 500
        import time

        time.sleep(0.1)
        speed = stats.upload_speed
        assert speed > 0
        assert speed < 10000  # Should be reasonable

    def test_progress_percent(self):
        """Test progress percentage calculation."""
        stats = UploadStats(total_bytes=1000)
        assert stats.progress_percent == 0.0

        stats.uploaded_bytes = 250
        assert stats.progress_percent == 25.0

        stats.uploaded_bytes = 1000
        assert stats.progress_percent == 100.0


class TestTusClientWithRetry:
    """Test TusClientWithRetry class."""

    def test_init(self):
        """Test client initialization."""
        client = TusClientWithRetry("http://localhost:8080/files")
        assert client.url == "http://localhost:8080/files"
        assert client.chunk_size == 1024 * 1024
        assert client.max_retries == 3
        assert client.retry_delay == 1.0
        assert client.checksum is True

    def test_init_custom_params(self):
        """Test client initialization with custom parameters."""
        client = TusClientWithRetry(
            "http://localhost:8080/files/",
            chunk_size=512 * 1024,
            max_retries=5,
            retry_delay=2.0,
            checksum=False,
        )
        assert client.url == "http://localhost:8080/files"
        assert client.chunk_size == 512 * 1024
        assert client.max_retries == 5
        assert client.retry_delay == 2.0
        assert client.checksum is False

    def test_upload_file_not_found(self):
        """Test upload with non-existent file."""
        client = TusClientWithRetry("http://localhost:8080/files")
        with pytest.raises(FileNotFoundError):
            client.upload_file("/nonexistent/file.bin")

    def test_upload_file_success(self):
        """Test successful file upload."""
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test data" * 1000)
            temp_file = f.name

        try:
            client = TusClientWithRetry(
                "http://localhost:8080/files", chunk_size=1024, max_retries=2
            )

            # Mock the HTTP requests
            with patch("resumable_upload.client.base.urlopen") as mock_urlopen:
                # Mock POST response (create upload)
                mock_post_response = MagicMock()
                mock_post_response.headers.get.return_value = "/files/test-upload-id"
                mock_post_response.__enter__.return_value = mock_post_response
                mock_post_response.__exit__.return_value = None

                # Mock PATCH response (upload chunks)
                mock_patch_response = MagicMock()
                mock_patch_response.__enter__.return_value = mock_patch_response
                mock_patch_response.__exit__.return_value = None

                # Configure mock to return different responses
                mock_urlopen.side_effect = [
                    mock_post_response,
                    *[mock_patch_response] * 10,
                ]

                # Track progress
                progress_calls = []

                def progress_callback(stats):
                    progress_calls.append(stats.progress_percent)

                # Upload file
                upload_url = client.upload_file(
                    temp_file,
                    metadata={"filename": "test.bin"},
                    progress_callback=progress_callback,
                )

                # Verify
                assert upload_url == "http://localhost:8080/files/test-upload-id"
                assert len(progress_calls) > 0
                assert progress_calls[-1] == 100.0

        finally:
            os.unlink(temp_file)

    def test_upload_with_retry_success(self):
        """Test successful upload after retry."""
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"X" * 2048)
            temp_file = f.name

        try:
            client = TusClientWithRetry(
                "http://localhost:8080/files",
                chunk_size=1024,
                max_retries=3,
                retry_delay=0.01,  # Very short delay for testing
            )

            with patch("resumable_upload.client.base.urlopen") as mock_urlopen:
                # Mock POST response
                mock_post_response = MagicMock()
                mock_post_response.headers.get.return_value = "/files/test-id"
                mock_post_response.__enter__.return_value = mock_post_response
                mock_post_response.__exit__.return_value = None

                # Mock PATCH responses - first fails, second succeeds
                call_count = [0]

                def side_effect_factory():
                    def side_effect(req):
                        call_count[0] += 1
                        if call_count[0] == 1:
                            # POST
                            return mock_post_response
                        elif call_count[0] == 2:
                            # First PATCH - fail
                            from urllib.error import URLError

                            raise URLError("Network error")
                        else:
                            # Subsequent PATCHes - success
                            mock_patch_success = MagicMock()
                            mock_patch_success.__enter__.return_value = mock_patch_success
                            mock_patch_success.__exit__.return_value = None
                            return mock_patch_success

                    return side_effect

                mock_urlopen.side_effect = side_effect_factory()

                # Track stats
                final_stats = []

                def progress_callback(stats):
                    final_stats.append(stats)

                # Upload file
                upload_url = client.upload_file(temp_file, progress_callback=progress_callback)

                # Verify
                assert upload_url == "http://localhost:8080/files/test-id"
                assert len(final_stats) > 0
                # Should have at least one retry
                assert any(s.chunks_retried > 0 for s in final_stats)

        finally:
            os.unlink(temp_file)

    def test_upload_with_all_retries_exhausted(self):
        """Test upload failure after all retries exhausted."""
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"X" * 1024)
            temp_file = f.name

        try:
            client = TusClientWithRetry(
                "http://localhost:8080/files",
                chunk_size=1024,
                max_retries=2,
                retry_delay=0.01,
            )

            with patch("resumable_upload.client.base.urlopen") as mock_urlopen:
                # Mock POST response
                mock_post_response = MagicMock()
                mock_post_response.headers.get.return_value = "/files/test-id"
                mock_post_response.__enter__.return_value = mock_post_response
                mock_post_response.__exit__.return_value = None

                # Mock PATCH to always fail
                from urllib.error import URLError

                def side_effect(req):
                    if req.get_method() == "POST":
                        return mock_post_response
                    else:
                        raise URLError("Network error")

                mock_urlopen.side_effect = side_effect

                # Upload should raise exception
                with pytest.raises(Exception, match="Failed to upload chunk|Network error"):
                    client.upload_file(temp_file)

        finally:
            os.unlink(temp_file)

    def test_checksum_enabled(self):
        """Test upload with checksum verification enabled."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test" * 100)
            temp_file = f.name

        try:
            client = TusClientWithRetry(
                "http://localhost:8080/files", chunk_size=400, checksum=True
            )

            with patch("resumable_upload.client.base.urlopen") as mock_urlopen:
                mock_post_response = MagicMock()
                mock_post_response.headers.get.return_value = "/files/test-id"
                mock_post_response.__enter__.return_value = mock_post_response
                mock_post_response.__exit__.return_value = None

                mock_patch_response = MagicMock()
                mock_patch_response.__enter__.return_value = mock_patch_response
                mock_patch_response.__exit__.return_value = None

                mock_urlopen.side_effect = [
                    mock_post_response,
                    mock_patch_response,
                ]

                client.upload_file(temp_file)

                # Verify PATCH request had checksum header (headers are case-insensitive)
                patch_call = mock_urlopen.call_args_list[1]
                request = patch_call[0][0]
                # Check for header (case-insensitive)
                headers_lower = {k.lower(): v for k, v in request.headers.items()}
                assert "upload-checksum" in headers_lower

        finally:
            os.unlink(temp_file)

    def test_checksum_disabled(self):
        """Test upload with checksum verification disabled."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test" * 100)
            temp_file = f.name

        try:
            client = TusClientWithRetry(
                "http://localhost:8080/files", chunk_size=400, checksum=False
            )

            with patch("resumable_upload.client.base.urlopen") as mock_urlopen:
                mock_post_response = MagicMock()
                mock_post_response.headers.get.return_value = "/files/test-id"
                mock_post_response.__enter__.return_value = mock_post_response
                mock_post_response.__exit__.return_value = None

                mock_patch_response = MagicMock()
                mock_patch_response.__enter__.return_value = mock_patch_response
                mock_patch_response.__exit__.return_value = None

                mock_urlopen.side_effect = [
                    mock_post_response,
                    mock_patch_response,
                ]

                client.upload_file(temp_file)

                # Verify PATCH request had NO checksum header
                patch_call = mock_urlopen.call_args_list[1]
                request = patch_call[0][0]
                # Check for header (case-insensitive)
                headers_lower = {k.lower(): v for k, v in request.headers.items()}
                assert "upload-checksum" not in headers_lower

        finally:
            os.unlink(temp_file)

    def test_metadata_encoding(self):
        """Test metadata is properly encoded."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            temp_file = f.name

        try:
            client = TusClientWithRetry("http://localhost:8080/files", chunk_size=100)

            with patch("resumable_upload.client.base.urlopen") as mock_urlopen:
                mock_post_response = MagicMock()
                mock_post_response.headers.get.return_value = "/files/test-id"
                mock_post_response.__enter__.return_value = mock_post_response
                mock_post_response.__exit__.return_value = None

                mock_patch_response = MagicMock()
                mock_patch_response.__enter__.return_value = mock_patch_response
                mock_patch_response.__exit__.return_value = None

                mock_urlopen.side_effect = [mock_post_response, mock_patch_response]

                client.upload_file(temp_file, metadata={"filename": "test.bin", "type": "binary"})

                # Verify POST request had metadata (headers are case-insensitive)
                post_call = mock_urlopen.call_args_list[0]
                request = post_call[0][0]
                headers_lower = {k.lower(): v for k, v in request.headers.items()}
                assert "upload-metadata" in headers_lower
                # Metadata should be base64 encoded
                metadata_header = headers_lower["upload-metadata"]
                assert "filename" in metadata_header
                assert "type" in metadata_header

        finally:
            os.unlink(temp_file)
