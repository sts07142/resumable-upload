"""Tests for new TUS client features: exceptions, fingerprinting, URL storage."""

import os
import tempfile

import pytest

from resumable_upload.exceptions import TusCommunicationError, TusUploadFailed
from resumable_upload.fingerprint import Fingerprint
from resumable_upload.url_storage import FileURLStorage


class TestExceptions:
    """Test custom exception classes."""

    def test_tus_communication_error_basic(self):
        """Test TusCommunicationError with basic message."""
        error = TusCommunicationError("Test error")
        assert str(error) == "Test error"
        assert error.message == "Test error"
        assert error.status_code is None
        assert error.response_content is None

    def test_tus_communication_error_full(self):
        """Test TusCommunicationError with all parameters."""
        error = TusCommunicationError(
            "Test error", status_code=500, response_content=b"Server error"
        )
        assert error.message == "Test error"
        assert error.status_code == 500
        assert error.response_content == b"Server error"

    def test_tus_communication_error_default_message(self):
        """Test TusCommunicationError with default message."""
        error = TusCommunicationError(None, status_code=404)
        assert "404" in str(error)
        assert error.status_code == 404

    def test_tus_upload_failed(self):
        """Test TusUploadFailed exception."""
        error = TusUploadFailed("Upload failed", status_code=500)
        assert str(error) == "Upload failed"
        assert error.status_code == 500
        assert isinstance(error, TusCommunicationError)


class TestFingerprint:
    """Test file fingerprinting functionality."""

    def test_fingerprint_from_file_path(self):
        """Test fingerprint generation from file path."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            f.write("test content")
            temp_path = f.name

        try:
            fingerprinter = Fingerprint()
            fp1 = fingerprinter.get_fingerprint(temp_path)
            fp2 = fingerprinter.get_fingerprint(temp_path)

            # Same file should generate same fingerprint
            assert fp1 == fp2
            # Fingerprint should contain size and MD5
            assert "size:" in fp1
            assert "--sha256:" in fp1
        finally:
            os.unlink(temp_path)

    def test_fingerprint_from_stream(self):
        """Test fingerprint generation from file stream."""
        with tempfile.NamedTemporaryFile(mode="w+b", delete=False) as f:
            f.write(b"test content")
            f.flush()
            temp_path = f.name

        try:
            fingerprinter = Fingerprint()
            with open(temp_path, "rb") as stream:
                original_pos = stream.tell()
                fp = fingerprinter.get_fingerprint(stream)
                # Stream position should be restored
                assert stream.tell() == original_pos

            assert "size:" in fp
            assert "--sha256:" in fp
        finally:
            os.unlink(temp_path)

    def test_fingerprint_different_files(self):
        """Test that different files generate different fingerprints."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f1:
            f1.write("content 1")
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f2:
            f2.write("content 2")
            path2 = f2.name

        try:
            fingerprinter = Fingerprint()
            fp1 = fingerprinter.get_fingerprint(path1)
            fp2 = fingerprinter.get_fingerprint(path2)

            assert fp1 != fp2
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_fingerprint_includes_size(self):
        """Test that fingerprint includes file size."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
            content = "x" * 12345
            f.write(content)
            temp_path = f.name

        try:
            fingerprinter = Fingerprint()
            fp = fingerprinter.get_fingerprint(temp_path)

            assert "size:12345" in fp
        finally:
            os.unlink(temp_path)


    def test_fingerprint_differs_for_files_with_same_first_64kb(self):
        """Files differing only after the first 64KB get distinct fingerprints."""
        block = b"x" * (64 * 1024)  # exactly 64KB prefix
        with tempfile.NamedTemporaryFile(delete=False) as f1:
            f1.write(block + b"AAAA")
            path1 = f1.name
        with tempfile.NamedTemporaryFile(delete=False) as f2:
            f2.write(block + b"BBBB")
            path2 = f2.name

        try:
            fingerprinter = Fingerprint()
            fp1 = fingerprinter.get_fingerprint(path1)
            fp2 = fingerprinter.get_fingerprint(path2)
            assert fp1 != fp2
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestURLStorage:
    """Test URL storage functionality."""

    def test_file_url_storage_set_and_get(self):
        """Test setting and getting URLs."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)
            fingerprint = "test_fp_123"
            url = "http://example.com/files/abc123"

            storage.set_url(fingerprint, url)
            retrieved_url = storage.get_url(fingerprint)

            assert retrieved_url == url
        finally:
            os.unlink(storage_path)

    def test_file_url_storage_update(self):
        """Test updating existing URLs."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)
            fingerprint = "test_fp_456"
            url1 = "http://example.com/files/first"
            url2 = "http://example.com/files/second"

            storage.set_url(fingerprint, url1)
            storage.set_url(fingerprint, url2)
            retrieved_url = storage.get_url(fingerprint)

            assert retrieved_url == url2
        finally:
            os.unlink(storage_path)

    def test_file_url_storage_remove(self):
        """Test removing URLs."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)
            fingerprint = "test_fp_789"
            url = "http://example.com/files/xyz789"

            storage.set_url(fingerprint, url)
            storage.remove_url(fingerprint)
            retrieved_url = storage.get_url(fingerprint)

            assert retrieved_url is None
        finally:
            os.unlink(storage_path)

    def test_file_url_storage_nonexistent_key(self):
        """Test getting URL for nonexistent fingerprint."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)
            retrieved_url = storage.get_url("nonexistent")

            assert retrieved_url is None
        finally:
            os.unlink(storage_path)

    def test_file_url_storage_multiple_keys(self):
        """Test storage with multiple keys."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)

            storage.set_url("fp1", "url1")
            storage.set_url("fp2", "url2")
            storage.set_url("fp3", "url3")

            assert storage.get_url("fp1") == "url1"
            assert storage.get_url("fp2") == "url2"
            assert storage.get_url("fp3") == "url3"
        finally:
            os.unlink(storage_path)

    def test_file_url_storage_concurrent_set_no_data_loss(self):
        """Concurrent set_url calls do not lose entries."""
        import threading

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)
            n = 50
            errors = []

            def worker(i):
                try:
                    storage.set_url(f"fp{i}", f"url{i}")
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            assert not errors
            # Every fingerprint must be present
            for i in range(n):
                assert storage.get_url(f"fp{i}") == f"url{i}", f"fp{i} missing"
        finally:
            os.unlink(storage_path)

    def test_save_data_atomic_no_corruption_on_crash(self):
        """Simulate crash mid-write: existing data must survive."""
        import unittest.mock

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)
            storage.set_url("fp_existing", "url_existing")

            # Simulate crash: make os.replace raise so the file is never overwritten
            with unittest.mock.patch("os.replace", side_effect=OSError("disk full")):
                with pytest.raises(OSError):
                    storage.set_url("fp_new", "url_new")

            # Original data must still be intact
            assert storage.get_url("fp_existing") == "url_existing"
        finally:
            os.unlink(storage_path)

    def test_get_url_consistent_during_concurrent_write(self):
        """get_url never returns corrupt data while set_url is writing."""
        import threading

        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as f:
            storage_path = f.name

        try:
            storage = FileURLStorage(storage_path)
            storage.set_url("stable", "stable_url")
            errors = []

            def writer():
                for i in range(20):
                    try:
                        storage.set_url(f"key{i}", f"val{i}")
                    except Exception as e:
                        errors.append(e)

            def reader():
                for _ in range(40):
                    try:
                        result = storage.get_url("stable")
                        # Once written, stable url must always be found or None (not corrupt)
                        assert result in ("stable_url", None)
                    except Exception as e:
                        errors.append(e)

            t1 = threading.Thread(target=writer)
            t2 = threading.Thread(target=reader)
            t1.start(); t2.start()
            t1.join(); t2.join()
            assert not errors
        finally:
            os.unlink(storage_path)
