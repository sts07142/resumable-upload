"""TUS protocol uploader for fine-grained upload control."""

import base64
import hashlib
import os
from typing import IO, Callable, Optional, Union
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from resumable_upload.exceptions import TusCommunicationError, TusUploadFailed


class Uploader:
    """TUS protocol uploader for fine-grained upload control.

    This class provides a standalone uploader that can be used independently
    when the upload URL is already known. It allows for manual chunk-by-chunk
    upload control.

    Example:
        >>> # Standalone usage
        >>> uploader = Uploader(
        ...     file_path="file.bin",
        ...     url="http://localhost:8080/files/abc123",
        ...     chunk_size=1024 * 1024,
        ...     headers={"Authorization": "Bearer token"},
        ... )
        >>> uploader.upload_chunk()  # Upload single chunk
        >>> uploader.upload()  # Upload entire file

        >>> # Created from client
        >>> client = TusClient("http://localhost:8080/files")
        >>> uploader = client.create_uploader("file.bin")
        >>> uploader.upload_chunk()
    """

    TUS_VERSION = "1.0.0"

    def __init__(
        self,
        url: str,
        file_path: Optional[str] = None,
        file_stream: Optional[IO] = None,
        chunk_size: Union[int, float] = 1024 * 1024,
        checksum: bool = True,
        metadata_encoding: str = "utf-8",
        headers: Optional[dict[str, str]] = None,
    ):
        """Initialize TUS uploader.

        Args:
            url: Upload URL (must already exist on server)
            file_path: Path to file to upload (required if file_stream not provided)
            file_stream: File stream to upload (alternative to file_path)
            chunk_size: Size of upload chunks in bytes (default: 1MB)
            checksum: Enable checksum verification (default: True)
            metadata_encoding: Encoding for metadata values (default: utf-8)
            headers: Optional custom headers to include in all requests

        Raises:
            ValueError: If neither file_path nor file_stream provided, or chunk_size < 1
        """
        if not file_path and not file_stream:
            raise ValueError("Either file_path or file_stream must be provided")

        if file_path and not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        if chunk_size < 1:
            raise ValueError(f"chunk_size must be at least 1 byte, got {chunk_size}")

        self.url = url
        self.file_path = file_path
        self.file_stream = file_stream
        self.chunk_size = int(chunk_size)
        self.checksum = checksum
        self.metadata_encoding = metadata_encoding
        self.headers = headers or {}

        # Initialize file stream
        if file_stream:
            self._file_handle = file_stream
            self._owns_file = False
            file_stream.seek(0, os.SEEK_END)
            self.file_size = file_stream.tell()
            file_stream.seek(0)
        else:
            self._file_handle = open(file_path, "rb")  # noqa: SIM115
            self._owns_file = True
            self.file_size = os.path.getsize(file_path)

        # Get current offset from server
        self.offset = self._get_offset()
        self._file_handle.seek(self.offset)

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - close file if we own it."""
        self.close()

    def close(self) -> None:
        """Close the file handle if we own it."""
        if self._owns_file and self._file_handle and not self._file_handle.closed:
            self._file_handle.close()

    def _get_offset(self) -> int:
        """Get the current upload offset from server."""
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            **self.headers,
        }

        try:
            req = Request(self.url, headers=headers, method="HEAD")
            with urlopen(req) as response:
                offset = response.headers.get("Upload-Offset")
                if offset is None:
                    raise TusCommunicationError("Server did not return Upload-Offset header")
                return int(offset)
        except HTTPError as e:
            raise TusCommunicationError(
                f"Failed to get offset: {e.reason}",
                status_code=e.code,
                response_content=e.read(),
            ) from e

    def _upload_chunk(self, data: bytes) -> None:
        """Upload a chunk of data."""
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Upload-Offset": str(self.offset),
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": str(len(data)),
            **self.headers,
        }

        # Add checksum if enabled
        if self.checksum:
            checksum_bytes = hashlib.sha1(data).digest()
            checksum_b64 = base64.b64encode(checksum_bytes).decode("ascii")
            headers["Upload-Checksum"] = f"sha1 {checksum_b64}"

        try:
            req = Request(self.url, data=data, headers=headers, method="PATCH")
            with urlopen(req) as response:
                # Update offset from server response
                new_offset = response.headers.get("Upload-Offset")
                if new_offset:
                    self.offset = int(new_offset)
                else:
                    self.offset += len(data)
        except HTTPError as e:
            raise TusUploadFailed(
                f"Failed to upload chunk at offset {self.offset}: {e.reason}",
                status_code=e.code,
                response_content=e.read(),
            ) from e

    def upload_chunk(self) -> bool:
        """Upload a single chunk.

        Returns:
            True if more chunks remain, False if upload is complete

        Raises:
            TusUploadFailed: If upload fails
        """
        if self.offset >= self.file_size:
            return False

        # Read chunk
        chunk_size = min(self.chunk_size, self.file_size - self.offset)
        self._file_handle.seek(self.offset)
        chunk = self._file_handle.read(chunk_size)

        if not chunk:
            return False

        # Upload chunk
        self._upload_chunk(chunk)

        return self.offset < self.file_size

    def upload(
        self,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_at: Optional[int] = None,
    ) -> str:
        """Upload the entire file or remaining chunks.

        Args:
            progress_callback: Optional callback function(uploaded_bytes, total_bytes)
            stop_at: Stop upload at this byte offset (for partial uploads)

        Returns:
            Upload URL

        Raises:
            TusUploadFailed: If upload fails
        """
        max_offset = stop_at if stop_at is not None else self.file_size

        while self.offset < max_offset:
            chunk_size = min(self.chunk_size, max_offset - self.offset)
            self._file_handle.seek(self.offset)
            chunk = self._file_handle.read(chunk_size)

            if not chunk:
                break

            self._upload_chunk(chunk)

            if progress_callback:
                progress_callback(self.offset, self.file_size)

        return self.url

    @property
    def progress(self) -> tuple[int, int]:
        """Get current upload progress.

        Returns:
            Tuple of (uploaded_bytes, total_bytes)
        """
        return (self.offset, self.file_size)

    @property
    def is_complete(self) -> bool:
        """Check if upload is complete.

        Returns:
            True if upload is complete, False otherwise
        """
        return self.offset >= self.file_size
