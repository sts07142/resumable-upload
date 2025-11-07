"""Test suite for storage module."""

import os
import shutil
import tempfile

import pytest

from resumable_upload.storage import SQLiteStorage


class TestSQLiteStorage:
    """Tests for SQLiteStorage."""

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

    def test_create_upload(self, storage):
        """Test creating an upload."""
        upload_id = "test-upload-1"
        upload_length = 1024
        metadata = {"filename": "test.txt"}

        storage.create_upload(upload_id, upload_length, metadata)

        upload = storage.get_upload(upload_id)
        assert upload is not None
        assert upload["upload_id"] == upload_id
        assert upload["upload_length"] == upload_length
        assert upload["offset"] == 0
        assert upload["metadata"] == metadata
        assert upload["completed"] is False

    def test_get_nonexistent_upload(self, storage):
        """Test getting a non-existent upload."""
        upload = storage.get_upload("nonexistent")
        assert upload is None

    def test_update_offset(self, storage):
        """Test updating upload offset."""
        upload_id = "test-upload-2"
        storage.create_upload(upload_id, 1024, {})

        storage.update_offset(upload_id, 512)
        upload = storage.get_upload(upload_id)
        assert upload["offset"] == 512
        assert upload["completed"] is False

        storage.update_offset(upload_id, 1024)
        upload = storage.get_upload(upload_id)
        assert upload["offset"] == 1024
        assert upload["completed"] is True

    def test_write_and_read_chunk(self, storage):
        """Test writing and reading chunks."""
        upload_id = "test-upload-3"
        storage.create_upload(upload_id, 100, {})

        # Write chunks
        storage.write_chunk(upload_id, 0, b"Hello ")
        storage.write_chunk(upload_id, 6, b"World!")

        # Read file
        data = storage.read_file(upload_id)
        assert data == b"Hello World!"

    def test_delete_upload(self, storage, temp_dir):
        """Test deleting an upload."""
        upload_id = "test-upload-4"
        storage.create_upload(upload_id, 1024, {})

        file_path = storage.get_file_path(upload_id)
        assert os.path.exists(file_path)

        storage.delete_upload(upload_id)
        assert storage.get_upload(upload_id) is None
        assert not os.path.exists(file_path)

    def test_get_file_path(self, storage, temp_dir):
        """Test getting file path."""
        upload_id = "test-upload-5"
        expected_path = os.path.join(temp_dir, "uploads", upload_id)
        assert storage.get_file_path(upload_id) == expected_path
