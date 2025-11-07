"""
File fingerprinting for unique identification of uploads.

Uses MD5 hash + file size to generate unique fingerprints for resumable uploads.
"""

import hashlib
import os
from typing import IO, Union


class Fingerprint:
    """
    Generate unique fingerprints for files to enable resumable uploads.

    Uses MD5 hash of file content combined with file size to create
    a unique identifier for each file.
    """

    BLOCK_SIZE = 65536  # 64KB blocks for hashing

    def get_fingerprint(self, file_source: Union[str, IO]) -> str:
        """
        Generate a unique fingerprint for a file.

        Args:
            file_source: Either a file path (str) or file stream (IO)

        Returns:
            str: Unique fingerprint in format "size:{size}--md5:{hash}"
        """
        if isinstance(file_source, str):
            # file_source is a path
            with open(file_source, "rb") as fs:
                return self._fingerprint_from_stream(fs)
        else:
            # file_source is a stream
            original_pos = file_source.tell()
            try:
                fingerprint = self._fingerprint_from_stream(file_source)
                return fingerprint
            finally:
                file_source.seek(original_pos)

    def _fingerprint_from_stream(self, fs: IO) -> str:
        """Generate fingerprint from file stream."""
        fs.seek(0)
        hasher = hashlib.md5()

        # Read first block for MD5
        buf = fs.read(self.BLOCK_SIZE)
        if isinstance(buf, str):
            buf = buf.encode("utf-8")
        hasher.update(buf)

        # Get file size
        fs.seek(0, os.SEEK_END)
        file_size = fs.tell()

        return f"size:{file_size}--md5:{hasher.hexdigest()}"
