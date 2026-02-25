"""Storage backend for managing upload state."""

import contextlib
import json
import os
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional


class Storage(ABC):
    """Abstract base class for storage backends."""

    @abstractmethod
    def create_upload(
        self,
        upload_id: str,
        upload_length: int,
        metadata: dict[str, str],
        expires_at: Optional[datetime] = None,
    ) -> None:
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

    @abstractmethod
    def get_expired_uploads(self) -> list[str]:
        """Get list of expired upload IDs."""
        pass

    @abstractmethod
    def cleanup_expired_uploads(self) -> int:
        """Delete expired uploads and return count deleted."""
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
        try:
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
            # Migration: add expires_at column for existing databases
            with contextlib.suppress(sqlite3.OperationalError):
                conn.execute("ALTER TABLE uploads ADD COLUMN expires_at TIMESTAMP")
            conn.commit()
        finally:
            conn.close()

    def create_upload(
        self,
        upload_id: str,
        upload_length: int,
        metadata: dict[str, str],
        expires_at: Optional[datetime] = None,
    ) -> None:
        """Create a new upload entry."""
        conn = sqlite3.connect(self.db_path)
        try:
            expires_at_str = expires_at.astimezone(timezone.utc).isoformat() if expires_at else None
            conn.execute(
                """
                INSERT INTO uploads (upload_id, upload_length, metadata, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (upload_id, upload_length, json.dumps(metadata), expires_at_str),
            )
            conn.commit()
        finally:
            conn.close()

        # Create empty file; roll back DB record if file creation fails
        file_path = self.get_file_path(upload_id)
        try:
            with open(file_path, "wb"):
                pass
        except OSError:
            self.delete_upload(upload_id)
            raise

    def get_upload(self, upload_id: str) -> Optional[dict[str, Any]]:
        """Get upload information."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM uploads WHERE upload_id = ?", (upload_id,))
            row = cursor.fetchone()
        finally:
            conn.close()

        if row is None:
            return None

        expires_at = None
        raw_expires = row["expires_at"]
        if raw_expires:
            try:
                dt = datetime.fromisoformat(raw_expires)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                expires_at = dt
            except (ValueError, AttributeError):
                pass

        return {
            "upload_id": row["upload_id"],
            "upload_length": row["upload_length"],
            "offset": row["offset"],
            "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
            "completed": bool(row["completed"]),
            "expires_at": expires_at,
        }

    def update_offset(self, upload_id: str, offset: int) -> None:
        """Update the current offset of an upload."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute(
                "UPDATE uploads SET offset = ?, completed = (? >= upload_length)"
                " WHERE upload_id = ?",
                (offset, offset, upload_id),
            )
            conn.commit()
        finally:
            conn.close()

    def delete_upload(self, upload_id: str) -> None:
        """Delete an upload entry."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.execute("DELETE FROM uploads WHERE upload_id = ?", (upload_id,))
            conn.commit()
        finally:
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

    def get_expired_uploads(self) -> list[str]:
        """Get list of expired upload IDs."""
        conn = sqlite3.connect(self.db_path)
        try:
            now = datetime.now(timezone.utc).isoformat()
            cursor = conn.execute(
                "SELECT upload_id FROM uploads WHERE expires_at IS NOT NULL AND expires_at < ?",
                (now,),
            )
            rows = cursor.fetchall()
        finally:
            conn.close()
        return [row[0] for row in rows]

    def cleanup_expired_uploads(self) -> int:
        """Delete expired uploads and return count deleted."""
        expired_ids = self.get_expired_uploads()
        for upload_id in expired_ids:
            self.delete_upload(upload_id)
        return len(expired_ids)
