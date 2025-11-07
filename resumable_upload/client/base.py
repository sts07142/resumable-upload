"""TUS protocol client implementation."""

import base64
import hashlib
import os
import re
from typing import IO, Callable, Optional, Union
from urllib.error import HTTPError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from resumable_upload.exceptions import TusCommunicationError, TusUploadFailed
from resumable_upload.fingerprint import Fingerprint
from resumable_upload.url_storage import URLStorage


class TusClient:
    """TUS protocol client for uploading files.

    This client implements TUS protocol version 1.0.0 as specified at:
    https://tus.io/protocols/resumable-upload.html

    Version Handling:
        - Uses TUS version 1.0.0
        - Sends "Tus-Resumable: 1.0.0" header with all requests
        - Compatible with TUS 1.0.0 compliant servers
        - Server must support version 1.0.0 to accept uploads

    Features:
        - File upload with configurable chunk size
        - Automatic resume of interrupted uploads
        - Progress tracking via callbacks
        - Optional SHA1 checksum verification
        - Metadata support for file information

    Example:
        >>> client = TusClient("http://localhost:8080/files")
        >>> url = client.upload_file(
        ...     "large_file.bin",
        ...     metadata={"filename": "large_file.bin"},
        ...     progress_callback=lambda up, total: print(f"{up}/{total}"),
        ... )
        >>> # Resume interrupted upload
        >>> client.resume_upload("large_file.bin", url)
    """

    TUS_VERSION = "1.0.0"

    def __init__(
        self,
        url: str,
        chunk_size: Union[int, float] = 1024 * 1024,
        checksum: bool = True,
        verify_tls_cert: bool = True,
        metadata_encoding: str = "utf-8",
        store_url: bool = False,
        url_storage: Optional[URLStorage] = None,
        fingerprinter: Optional[Fingerprint] = None,
    ):
        """Initialize TUS client.

        Args:
            url: Base URL of TUS server
            chunk_size: Size of upload chunks in bytes (default: 1MB). Can be int or float.
            checksum: Enable checksum verification (default: True)
            verify_tls_cert: Verify TLS certificates (default: True)
            metadata_encoding: Encoding for metadata values (default: utf-8)
            store_url: Store upload URLs for resumability (default: False)
            url_storage: Custom URL storage implementation
            fingerprinter: Custom fingerprint implementation

        Raises:
            ValueError: If chunk_size is less than 1
        """
        if chunk_size < 1:
            raise ValueError(f"chunk_size must be at least 1 byte, got {chunk_size}")
        self.url = url.rstrip("/")
        self.chunk_size = int(chunk_size)
        self.checksum = checksum
        self.verify_tls_cert = verify_tls_cert
        self.metadata_encoding = metadata_encoding
        self.store_url = store_url
        self.url_storage = url_storage
        self.fingerprinter = fingerprinter or Fingerprint()

    def upload_file(
        self,
        file_path: Optional[str] = None,
        file_stream: Optional[IO] = None,
        metadata: Optional[dict[str, str]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        stop_at: Optional[int] = None,
    ) -> str:
        """Upload a file to the server.

        Args:
            file_path: Path to file to upload (required if file_stream not provided)
            file_stream: File stream to upload (alternative to file_path)
            metadata: Optional metadata dictionary
            progress_callback: Optional callback function(uploaded_bytes, total_bytes)
            stop_at: Stop upload at this byte offset (for partial uploads)

        Returns:
            URL of the uploaded file

        Raises:
            ValueError: If neither file_path nor file_stream provided
            FileNotFoundError: If file doesn't exist
            TusCommunicationError: If upload fails
        """
        if not file_path and not file_stream:
            raise ValueError("Either file_path or file_stream must be provided")

        if file_path and not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        # Get file size
        if file_stream:
            file_stream.seek(0, os.SEEK_END)
            file_size = file_stream.tell()
            file_stream.seek(0)
        else:
            file_size = os.path.getsize(file_path)

        metadata = metadata or {}

        # Add filename to metadata if not present and we have a file_path
        if "filename" not in metadata and file_path:
            metadata["filename"] = os.path.basename(file_path)

        # Check for stored URL if enabled
        upload_url = None
        if self.store_url and self.url_storage:
            fingerprint = self.fingerprinter.get_fingerprint(file_path or file_stream)
            upload_url = self.url_storage.get_url(fingerprint)

        # Create upload if no stored URL
        if not upload_url:
            upload_url = self._create_upload(file_size, metadata)
            if self.store_url and self.url_storage:
                fingerprint = self.fingerprinter.get_fingerprint(file_path or file_stream)
                self.url_storage.set_url(fingerprint, upload_url)

        # Upload file in chunks
        if file_stream:
            fs = file_stream
            fs.seek(0)
        else:
            fs = open(file_path, "rb")  # noqa: SIM115

        try:
            offset = self._get_offset(upload_url)
            fs.seek(offset)

            max_offset = stop_at if stop_at is not None else file_size

            while offset < max_offset:
                chunk_size = min(self.chunk_size, max_offset - offset)
                chunk = fs.read(chunk_size)
                if not chunk:
                    break

                self._upload_chunk(upload_url, offset, chunk)
                offset += len(chunk)

                if progress_callback:
                    progress_callback(offset, file_size)
        finally:
            if not file_stream and file_path:
                fs.close()

        return upload_url

    def resume_upload(
        self,
        file_path: str,
        upload_url: str,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> str:
        """Resume an interrupted upload.

        Args:
            file_path: Path to file to upload
            upload_url: URL of the existing upload
            progress_callback: Optional callback function(uploaded_bytes, total_bytes)

        Returns:
            URL of the uploaded file

        Raises:
            FileNotFoundError: If file doesn't exist
            HTTPError: If upload fails
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)

        # Get current offset
        offset = self._get_offset(upload_url)

        # Resume upload from current offset
        with open(file_path, "rb") as f:
            f.seek(offset)
            while offset < file_size:
                chunk = f.read(self.chunk_size)
                if not chunk:
                    break

                self._upload_chunk(upload_url, offset, chunk)
                offset += len(chunk)

                if progress_callback:
                    progress_callback(offset, file_size)

        return upload_url

    def delete_upload(self, upload_url: str) -> None:
        """Delete an upload from the server.

        Args:
            upload_url: URL of the upload to delete

        Raises:
            HTTPError: If deletion fails
        """
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
        }

        req = Request(upload_url, headers=headers, method="DELETE")
        try:
            with urlopen(req):
                pass
        except HTTPError as e:
            if e.code != 404:
                raise

    def _create_upload(self, file_size: int, metadata: dict[str, str]) -> str:
        """Create a new upload on the server."""
        # Encode metadata
        encoded_metadata = self.encode_metadata(metadata)

        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Upload-Length": str(file_size),
        }

        if encoded_metadata:
            headers["Upload-Metadata"] = ",".join(encoded_metadata)

        try:
            req = Request(self.url, headers=headers, method="POST")
            with urlopen(req) as response:
                location = response.headers.get("Location")
                if not location:
                    raise TusCommunicationError("Server did not return Location header")

                # Handle relative URLs
                if not location.startswith("http"):
                    location = urljoin(self.url, location)

                return location
        except HTTPError as e:
            raise TusCommunicationError(
                f"Failed to create upload: {e.reason}",
                status_code=e.code,
                response_content=e.read(),
            ) from e

    def encode_metadata(self, metadata: dict[str, str]) -> list:
        """
        Encode metadata according to TUS protocol specification.

        Args:
            metadata: Dictionary of metadata key-value pairs

        Returns:
            List of encoded metadata strings

        Raises:
            ValueError: If metadata keys contain invalid characters
        """
        encoded_list = []
        for key, value in metadata.items():
            key_str = str(key)

            # Validate key does not contain spaces or commas
            if re.search(r"^$|[\s,]+", key_str):
                raise ValueError(
                    f'Upload-metadata key "{key_str}" cannot be empty nor contain spaces or commas.'
                )

            value_bytes = value.encode(self.metadata_encoding)
            encoded_value = base64.b64encode(value_bytes).decode("ascii")
            encoded_list.append(f"{key_str} {encoded_value}")

        return encoded_list

    def _get_offset(self, upload_url: str) -> int:
        """Get the current upload offset."""
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
        }

        try:
            req = Request(upload_url, headers=headers, method="HEAD")
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

    def _upload_chunk(self, upload_url: str, offset: int, data: bytes) -> None:
        """Upload a chunk of data."""
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Upload-Offset": str(offset),
            "Content-Type": "application/offset+octet-stream",
            "Content-Length": str(len(data)),
        }

        # Add checksum if enabled
        if self.checksum:
            checksum_bytes = hashlib.sha1(data).digest()
            checksum_b64 = base64.b64encode(checksum_bytes).decode("ascii")
            headers["Upload-Checksum"] = f"sha1 {checksum_b64}"

        try:
            req = Request(upload_url, data=data, headers=headers, method="PATCH")
            with urlopen(req):
                pass
        except HTTPError as e:
            raise TusUploadFailed(
                f"Failed to upload chunk at offset {offset}: {e.reason}",
                status_code=e.code,
                response_content=e.read(),
            ) from e

    def get_file_size(self, file_source: Union[str, IO]) -> int:
        """
        Get the size of a file.

        Args:
            file_source: Either a file path (str) or file stream (IO)

        Returns:
            File size in bytes
        """
        if isinstance(file_source, str):
            return os.path.getsize(file_source)
        else:
            current_pos = file_source.tell()
            file_source.seek(0, os.SEEK_END)
            size = file_source.tell()
            file_source.seek(current_pos)
            return size

    def get_file_stream(self, file_source: Union[str, IO]) -> IO:
        """
        Get a file stream from a file path or stream.

        Args:
            file_source: Either a file path (str) or file stream (IO)

        Returns:
            File stream object
        """
        if isinstance(file_source, str):
            return open(file_source, "rb")
        else:
            file_source.seek(0)
            return file_source
