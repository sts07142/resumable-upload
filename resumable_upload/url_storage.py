"""
URL storage interface and implementations for resumable uploads.

Allows storing and retrieving upload URLs based on file fingerprints,
enabling resumable uploads across sessions.
"""

import json
import os
from abc import ABC, abstractmethod
from typing import Optional


class URLStorage(ABC):
    """Abstract interface for URL storage implementations."""

    @abstractmethod
    def get_url(self, fingerprint: str) -> Optional[str]:
        """
        Retrieve upload URL for a given file fingerprint.

        Args:
            fingerprint: Unique file fingerprint

        Returns:
            Upload URL if found, None otherwise
        """
        pass

    @abstractmethod
    def set_url(self, fingerprint: str, url: str) -> None:
        """
        Store upload URL for a given file fingerprint.

        Args:
            fingerprint: Unique file fingerprint
            url: Upload URL to store
        """
        pass

    @abstractmethod
    def remove_url(self, fingerprint: str) -> None:
        """
        Remove stored URL for a given file fingerprint.

        Args:
            fingerprint: Unique file fingerprint
        """
        pass


class FileURLStorage(URLStorage):
    """
    File-based URL storage using JSON.

    Stores upload URLs in a JSON file for persistence across sessions.
    """

    def __init__(self, storage_path: str = ".tus_urls.json"):
        """
        Initialize file-based URL storage.

        Args:
            storage_path: Path to JSON file for storing URLs
        """
        self.storage_path = storage_path
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Create storage file if it doesn't exist."""
        if not os.path.exists(self.storage_path):
            with open(self.storage_path, "w") as f:
                json.dump({}, f)

    def _load_data(self) -> dict:
        """Load data from storage file."""
        try:
            with open(self.storage_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return {}

    def _save_data(self, data: dict):
        """Save data to storage file."""
        with open(self.storage_path, "w") as f:
            json.dump(data, f, indent=2)

    def get_url(self, fingerprint: str) -> Optional[str]:
        """Retrieve upload URL for fingerprint."""
        data = self._load_data()
        return data.get(fingerprint)

    def set_url(self, fingerprint: str, url: str) -> None:
        """Store upload URL for fingerprint."""
        data = self._load_data()
        data[fingerprint] = url
        self._save_data(data)

    def remove_url(self, fingerprint: str) -> None:
        """Remove URL for fingerprint."""
        data = self._load_data()
        if fingerprint in data:
            del data[fingerprint]
            self._save_data(data)
