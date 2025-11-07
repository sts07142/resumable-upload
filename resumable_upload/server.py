"""TUS protocol server implementation."""

import hashlib
import logging
import uuid
from http.server import BaseHTTPRequestHandler
from typing import Any, Optional

from resumable_upload.storage import SQLiteStorage, Storage

logger = logging.getLogger(__name__)


class TusServer:
    """TUS protocol server implementation.

    This server implements TUS protocol version 1.0.0 as specified at:
    https://tus.io/protocols/resumable-upload.html

    Version Handling:
        - Supports only TUS version 1.0.0
        - Requires clients to send "Tus-Resumable: 1.0.0" header
        - Returns 412 Precondition Failed for other versions
        - This is compliant with TUS specification

    Supported Extensions:
        - creation: Upload creation via POST
        - termination: Upload deletion via DELETE
        - checksum: SHA1 checksum verification

    Example:
        >>> storage = SQLiteStorage()
        >>> server = TusServer(storage=storage, base_path="/files")
        >>> status, headers, body = server.handle_request(
        ...     "POST",
        ...     "/files",
        ...     {"tus-resumable": "1.0.0", "upload-length": "1024"},
        ...     b"",
        ... )
    """

    TUS_VERSION = "1.0.0"
    SUPPORTED_EXTENSIONS = ["creation", "termination", "checksum"]

    def __init__(
        self,
        storage: Optional[Storage] = None,
        base_path: str = "/files",
        max_size: int = 0,
    ):
        """Initialize TUS server.

        Args:
            storage: Storage backend (defaults to SQLiteStorage)
            base_path: Base URL path for uploads
            max_size: Maximum upload size in bytes (0 = unlimited)
        """
        self.storage = storage or SQLiteStorage()
        self.base_path = base_path.rstrip("/")
        self.max_size = max_size

    def handle_request(
        self, method: str, path: str, headers: dict[str, str], body: bytes = b""
    ) -> tuple[int, dict[str, str], bytes]:
        """Handle an incoming HTTP request.

        Args:
            method: HTTP method
            path: Request path
            headers: Request headers
            body: Request body

        Returns:
            Tuple of (status_code, response_headers, response_body)

        Note:
            According to TUS protocol specification (https://tus.io/protocols/resumable-upload.html):
            - The server checks for exact version match with Tus-Resumable header
            - This implementation only supports TUS version 1.0.0
            - Clients must send "Tus-Resumable: 1.0.0" header in all requests (except OPTIONS)
            - If version doesn't match, server returns 412 Precondition Failed
            - This is standard TUS behavior - servers are not required to support multiple versions
        """
        logger.info(f"Received {method} request for {path}")

        # Normalize headers to lowercase
        headers = {k.lower(): v for k, v in headers.items()}

        # Check TUS version (required by TUS spec for all non-OPTIONS requests)
        # Per spec: Server MUST check Tus-Resumable header and return 412 if not supported
        if method != "OPTIONS":
            tus_version = headers.get("tus-resumable")
            if tus_version != self.TUS_VERSION:
                logger.warning(f"Invalid TUS version: {tus_version}, expected {self.TUS_VERSION}")
                return (
                    412,
                    {"Tus-Resumable": self.TUS_VERSION},
                    b"Precondition Failed: Invalid TUS version",
                )

        # Route request
        if method == "OPTIONS":
            return self._handle_options(path, headers)
        elif method == "POST" and path == self.base_path:
            return self._handle_create(headers, body)
        elif method == "HEAD" and path.startswith(self.base_path + "/"):
            upload_id = path[len(self.base_path) + 1 :]
            return self._handle_head(upload_id, headers)
        elif method == "PATCH" and path.startswith(self.base_path + "/"):
            upload_id = path[len(self.base_path) + 1 :]
            return self._handle_patch(upload_id, headers, body)
        elif method == "DELETE" and path.startswith(self.base_path + "/"):
            upload_id = path[len(self.base_path) + 1 :]
            return self._handle_delete(upload_id, headers)
        else:
            logger.warning(f"Route not found: {method} {path}")
            return (404, {}, b"Not Found")

    def _handle_options(
        self, path: str, headers: dict[str, str]
    ) -> tuple[int, dict[str, str], bytes]:
        """Handle OPTIONS request for capability discovery."""
        logger.debug("Handling OPTIONS request")
        response_headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Tus-Version": self.TUS_VERSION,
            "Tus-Extension": ",".join(self.SUPPORTED_EXTENSIONS),
        }

        if self.max_size > 0:
            response_headers["Tus-Max-Size"] = str(self.max_size)

        return (204, response_headers, b"")

    def _handle_create(
        self, headers: dict[str, str], body: bytes
    ) -> tuple[int, dict[str, str], bytes]:
        """Handle POST request to create a new upload."""
        upload_length_str = headers.get("upload-length")
        if not upload_length_str:
            logger.error("Missing Upload-Length header")
            return (400, {}, b"Missing Upload-Length header")

        try:
            upload_length = int(upload_length_str)
        except ValueError:
            logger.error(f"Invalid Upload-Length header: {upload_length_str}")
            return (400, {}, b"Invalid Upload-Length header")

        if self.max_size > 0 and upload_length > self.max_size:
            logger.warning(f"Upload size {upload_length} exceeds maximum {self.max_size}")
            return (413, {}, b"Upload exceeds maximum size")

        # Parse metadata
        metadata = {}
        upload_metadata = headers.get("upload-metadata", "")
        if upload_metadata:
            for pair in upload_metadata.split(","):
                pair = pair.strip()
                if " " in pair:
                    key, value = pair.split(" ", 1)
                    # Decode base64 value
                    try:
                        import base64

                        metadata[key] = base64.b64decode(value).decode("utf-8")
                    except Exception:
                        metadata[key] = value

        # Generate upload ID
        upload_id = str(uuid.uuid4())

        # Create upload
        self.storage.create_upload(upload_id, upload_length, metadata)
        logger.info(f"Created upload {upload_id} with length {upload_length}, metadata: {metadata}")

        # Return response
        response_headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Location": f"{self.base_path}/{upload_id}",
            "Upload-Offset": "0",
        }

        return (201, response_headers, b"")

    def _handle_head(
        self, upload_id: str, headers: dict[str, str]
    ) -> tuple[int, dict[str, str], bytes]:
        """Handle HEAD request to get upload offset."""
        upload = self.storage.get_upload(upload_id)
        if not upload:
            logger.warning(f"Upload not found: {upload_id}")
            return (404, {}, b"Upload not found")

        logger.debug(
            f"HEAD request for upload {upload_id}: "
            f"offset={upload['offset']}, length={upload['upload_length']}"
        )
        response_headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Upload-Offset": str(upload["offset"]),
            "Upload-Length": str(upload["upload_length"]),
            "Cache-Control": "no-store",
        }

        return (200, response_headers, b"")

    def _handle_patch(
        self, upload_id: str, headers: dict[str, str], body: bytes
    ) -> tuple[int, dict[str, str], bytes]:
        """Handle PATCH request to append data to upload."""
        upload = self.storage.get_upload(upload_id)
        if not upload:
            logger.warning(f"Upload not found: {upload_id}")
            return (404, {}, b"Upload not found")

        # Check content type
        content_type = headers.get("content-type", "")
        if content_type != "application/offset+octet-stream":
            logger.error(f"Invalid Content-Type: {content_type}")
            return (400, {}, b"Invalid Content-Type")

        # Check upload offset
        upload_offset_str = headers.get("upload-offset")
        if not upload_offset_str:
            logger.error("Missing Upload-Offset header")
            return (400, {}, b"Missing Upload-Offset header")

        try:
            upload_offset = int(upload_offset_str)
        except ValueError:
            logger.error(f"Invalid Upload-Offset header: {upload_offset_str}")
            return (400, {}, b"Invalid Upload-Offset header")

        if upload_offset != upload["offset"]:
            logger.error(
                f"Upload-Offset mismatch: expected {upload['offset']}, got {upload_offset}"
            )
            return (409, {}, b"Upload-Offset mismatch")

        # Verify checksum if provided
        upload_checksum = headers.get("upload-checksum")
        if upload_checksum:
            try:
                algo, checksum = upload_checksum.split(" ", 1)
                if algo == "sha1":
                    computed = hashlib.sha1(body).hexdigest()
                    import base64

                    provided = base64.b64decode(checksum).hex()
                    if computed != provided:
                        logger.error(f"Checksum mismatch for upload {upload_id}")
                        return (460, {}, b"Checksum mismatch")
            except Exception as e:
                logger.error(f"Invalid Upload-Checksum header: {e}")
                return (400, {}, b"Invalid Upload-Checksum header")

        # Write chunk
        self.storage.write_chunk(upload_id, upload_offset, body)
        new_offset = upload_offset + len(body)
        self.storage.update_offset(upload_id, new_offset)

        logger.info(
            f"PATCH upload {upload_id}: wrote {len(body)} bytes, "
            f"new offset: {new_offset}/{upload['upload_length']}"
        )

        # Return response
        response_headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Upload-Offset": str(new_offset),
        }

        return (204, response_headers, b"")

    def _handle_delete(
        self, upload_id: str, headers: dict[str, str]
    ) -> tuple[int, dict[str, str], bytes]:
        """Handle DELETE request to terminate upload."""
        upload = self.storage.get_upload(upload_id)
        if not upload:
            logger.warning(f"Upload not found for deletion: {upload_id}")
            return (404, {}, b"Upload not found")

        self.storage.delete_upload(upload_id)
        logger.info(f"Deleted upload {upload_id}")

        response_headers = {
            "Tus-Resumable": self.TUS_VERSION,
        }

        return (204, response_headers, b"")


class TusHTTPRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for TUS server."""

    tus_server: TusServer = None

    def do_OPTIONS(self) -> None:
        """Handle OPTIONS request."""
        self._handle_request("OPTIONS")

    def do_POST(self) -> None:
        """Handle POST request."""
        self._handle_request("POST")

    def do_HEAD(self) -> None:
        """Handle HEAD request."""
        self._handle_request("HEAD")

    def do_PATCH(self) -> None:
        """Handle PATCH request."""
        self._handle_request("PATCH")

    def do_DELETE(self) -> None:
        """Handle DELETE request."""
        self._handle_request("DELETE")

    def _handle_request(self, method: str) -> None:
        """Handle incoming request."""
        # Read body for POST/PATCH
        body = b""
        if method in ("POST", "PATCH"):
            content_length = int(self.headers.get("Content-Length", 0))
            if content_length > 0:
                body = self.rfile.read(content_length)

        # Convert headers to dict
        headers = dict(self.headers)

        # Handle request
        status, response_headers, response_body = self.tus_server.handle_request(
            method, self.path, headers, body
        )

        # Send response
        self.send_response(status)
        for key, value in response_headers.items():
            self.send_header(key, value)
        self.end_headers()
        if response_body:
            self.wfile.write(response_body)

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress default logging."""
        pass
