"""TUS protocol client implementation."""

import base64
import hashlib
import os
import re
from typing import IO, Any, Callable, Optional, Union
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
        headers: Optional[dict[str, str]] = None,
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
            headers: Optional custom headers to include in all requests

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
        self.headers = headers or {}

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
            **self.headers,
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
            **self.headers,
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
            **self.headers,
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
            **self.headers,
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

    def update_headers(self, headers: dict[str, str]) -> None:
        """Update custom headers for all requests.

        Args:
            headers: Dictionary of header names to values

        Example:
            >>> client = TusClient("http://localhost:8080/files")
            >>> client.update_headers({"Authorization": "Bearer token"})
            >>> # Update existing headers
            >>> client.update_headers({"X-API-Key": "new-key"})
        """
        self.headers.update(headers)

    def get_headers(self) -> dict[str, str]:
        """Get current custom headers.

        Returns:
            Dictionary of current custom headers

        Example:
            >>> client = TusClient("http://localhost:8080/files")
            >>> client.update_headers({"Authorization": "Bearer token"})
            >>> headers = client.get_headers()
            >>> print(headers)  # {"Authorization": "Bearer token"}
        """
        return self.headers.copy()

    def get_metadata(self, upload_url: str) -> dict[str, str]:
        """Get metadata for an upload.

        Args:
            upload_url: URL of the upload

        Returns:
            Dictionary of metadata key-value pairs

        Raises:
            TusCommunicationError: If request fails or metadata cannot be parsed

        Example:
            >>> client = TusClient("http://localhost:8080/files")
            >>> metadata = client.get_metadata("http://localhost:8080/files/abc123")
            >>> # {"filename": "test.bin", "content-type": "application/octet-stream"}
        """
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            **self.headers,
        }

        try:
            req = Request(upload_url, headers=headers, method="HEAD")
            with urlopen(req) as response:
                upload_metadata = response.headers.get("Upload-Metadata")
                if not upload_metadata:
                    return {}

                # Parse metadata
                metadata = {}
                for pair in upload_metadata.split(","):
                    pair = pair.strip()
                    if " " in pair:
                        key, value = pair.split(" ", 1)
                        # Decode base64 value
                        try:
                            decoded_value = base64.b64decode(value).decode(self.metadata_encoding)
                            metadata[key] = decoded_value
                        except Exception:
                            # If decoding fails, use raw value
                            metadata[key] = value

                return metadata
        except HTTPError as e:
            raise TusCommunicationError(
                f"Failed to get metadata: {e.reason}",
                status_code=e.code,
                response_content=e.read(),
            ) from e

    def get_upload_info(self, upload_url: str) -> dict[str, Any]:
        """Get upload information including offset, length, and metadata.

        Args:
            upload_url: URL of the upload

        Returns:
            Dictionary containing:
                - offset (int): Current upload offset in bytes
                - length (int): Total upload length in bytes
                - complete (bool): Whether upload is complete
                - metadata (dict): Upload metadata

        Raises:
            TusCommunicationError: If request fails

        Example:
            >>> client = TusClient("http://localhost:8080/files")
            >>> info = client.get_upload_info("http://localhost:8080/files/abc123")
            >>> print(f"Progress: {info['offset']}/{info['length']}")
            >>> print(f"Complete: {info['complete']}")
        """
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            **self.headers,
        }

        try:
            req = Request(upload_url, headers=headers, method="HEAD")
            with urlopen(req) as response:
                offset_str = response.headers.get("Upload-Offset")
                length_str = response.headers.get("Upload-Length")

                offset = int(offset_str) if offset_str else 0
                length = int(length_str) if length_str else 0
                complete = length > 0 and offset >= length

                # Get metadata
                metadata = {}
                upload_metadata = response.headers.get("Upload-Metadata")
                if upload_metadata:
                    for pair in upload_metadata.split(","):
                        pair = pair.strip()
                        if " " in pair:
                            key, value = pair.split(" ", 1)
                            try:
                                decoded_value = base64.b64decode(value).decode(
                                    self.metadata_encoding
                                )
                                metadata[key] = decoded_value
                            except Exception:
                                metadata[key] = value

                return {
                    "offset": offset,
                    "length": length,
                    "complete": complete,
                    "metadata": metadata,
                }
        except HTTPError as e:
            raise TusCommunicationError(
                f"Failed to get upload info: {e.reason}",
                status_code=e.code,
                response_content=e.read(),
            ) from e

    def get_server_info(self) -> dict[str, Union[str, list[str], Optional[int]]]:
        """Get server information and capabilities via OPTIONS request.

        Returns:
            Dictionary containing:
                - version (str): TUS protocol version supported by server
                - extensions (list[str]): List of supported TUS extensions
                - max_size (int | None): Maximum upload size in bytes (None if unlimited)

        Raises:
            TusCommunicationError: If request fails

        Example:
            >>> client = TusClient("http://localhost:8080/files")
            >>> info = client.get_server_info()
            >>> print(f"TUS Version: {info['version']}")
            >>> print(f"Extensions: {info['extensions']}")
            >>> print(f"Max Size: {info['max_size']}")
        """
        try:
            req = Request(self.url, method="OPTIONS")
            with urlopen(req) as response:
                tus_version = response.headers.get("Tus-Version", self.TUS_VERSION)
                tus_extension = response.headers.get("Tus-Extension", "")
                tus_max_size = response.headers.get("Tus-Max-Size")

                extensions = (
                    [ext.strip() for ext in tus_extension.split(",") if ext.strip()]
                    if tus_extension
                    else []
                )

                max_size = int(tus_max_size) if tus_max_size else None

                return {
                    "version": tus_version,
                    "extensions": extensions,
                    "max_size": max_size,
                }
        except HTTPError as e:
            raise TusCommunicationError(
                f"Failed to get server info: {e.reason}",
                status_code=e.code,
                response_content=e.read(),
            ) from e
