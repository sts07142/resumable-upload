"""Storage backend for managing upload state."""

import json
import os
import sqlite3
from abc import ABC, abstractmethod
from typing import Any, Optional


class Storage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def create_upload(self, upload_id: str, upload_length: int, metadata: dict[str, str]) -> None:
        """Create a new upload entry."""
        pass

    @abstractmethod
    def get_upload(self, upload_id: str) -> Optional[dict[str, Any]]:
        """Get upload information."""
        pass

    @abstractmethod
    def update_offset(self, upload_id: str, offset: int) -> None:
        """Update the current offset of an upload."""
        pass

    @abstractmethod
    def delete_upload(self, upload_id: str) -> None:
        """Delete an upload entry."""
        pass

    @abstractmethod
    def write_chunk(self, upload_id: str, offset: int, data: bytes) -> None:
        """Write a chunk of data to the upload file."""
        pass

    @abstractmethod
    def read_file(self, upload_id: str) -> bytes:
        """Read the complete uploaded file."""
        pass

    @abstractmethod
    def get_file_path(self, upload_id: str) -> str:
        """Get the file path for an upload."""
        pass


class SQLiteStorage(Storage):
    """SQLite-based storage backend."""

    def __init__(self, db_path: str = "uploads.db", upload_dir: str = "uploads"):
        """Initialize SQLite storage.

        Args:
            db_path: Path to SQLite database file
            upload_dir: Directory to store uploaded files
        """
        self.db_path = db_path
        self.upload_dir = upload_dir
        os.makedirs(upload_dir, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize database schema."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
                upload_id TEXT PRIMARY KEY,
                upload_length INTEGER NOT NULL,
                offset INTEGER DEFAULT 0,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed BOOLEAN DEFAULT 0
            )
            """
        )
        conn.commit()
        conn.close()

    def create_upload(self, upload_id: str, upload_length: int, metadata: dict[str, str]) -> None:
        """Create a new upload entry."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """
            INSERT INTO uploads (upload_id, upload_length, metadata)
            VALUES (?, ?, ?)
            """,
            (upload_id, upload_length, json.dumps(metadata)),
        )
        conn.commit()
        conn.close()

        # Create empty file
        file_path = self.get_file_path(upload_id)
        with open(file_path, "wb"):
            pass

    def get_upload(self, upload_id: str) -> Optional[dict[str, Any]]:
        """Get upload information."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute("SELECT * FROM uploads WHERE upload_id = ?", (upload_id,))
        row = cursor.fetchone()
        conn.close()

        if row is None:
            return None

        return {
            "upload_id": row["upload_id"],
            "upload_length": row["upload_length"],
            "offset": row["offset"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "completed": bool(row["completed"]),
        }

    def update_offset(self, upload_id: str, offset: int) -> None:
        """Update the current offset of an upload."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("SELECT upload_length FROM uploads WHERE upload_id = ?", (upload_id,))
        row = cursor.fetchone()

        if row:
            upload_length = row[0]
            completed = offset >= upload_length
            conn.execute(
                """
                UPDATE uploads
                SET offset = ?, completed = ?
                WHERE upload_id = ?
                """,
                (offset, completed, upload_id),
            )
            conn.commit()
        conn.close()

    def delete_upload(self, upload_id: str) -> None:
        """Delete an upload entry."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM uploads WHERE upload_id = ?", (upload_id,))
        conn.commit()
        conn.close()

        # Delete file if exists
        file_path = self.get_file_path(upload_id)
        if os.path.exists(file_path):
            os.remove(file_path)

    def write_chunk(self, upload_id: str, offset: int, data: bytes) -> None:
        """Write a chunk of data to the upload file."""
        file_path = self.get_file_path(upload_id)
        # Ensure file exists before writing
        if not os.path.exists(file_path):
            with open(file_path, "wb") as f:
                pass
        with open(file_path, "r+b") as f:
            f.seek(offset)
            f.write(data)

    def read_file(self, upload_id: str) -> bytes:
        """Read the complete uploaded file."""
        file_path = self.get_file_path(upload_id)
        with open(file_path, "rb") as f:
            return f.read()

    def get_file_path(self, upload_id: str) -> str:
        """Get the file path for an upload."""
        return os.path.join(self.upload_dir, upload_id)
