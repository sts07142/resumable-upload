#!/usr/bin/env python3
"""
Advanced TUS client example with retry logic and robust error handling.

This example demonstrates:
1. Chunked file uploads with configurable chunk size
2. Automatic retry on failures with exponential backoff
3. Checksum verification for data integrity
4. Progress tracking with detailed statistics
5. Error recovery and detailed logging

Note: TUS protocol uploads chunks sequentially (not in parallel) because each
chunk must be uploaded at the correct offset. The server validates that the
Upload-Offset header matches the current file position.
"""

import base64
import hashlib
import logging
import os
import sys
import time
from dataclasses import dataclass
from threading import Lock
from typing import Callable, Optional, Union
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen


@dataclass
class UploadStats:
    """Statistics for upload progress."""

    total_bytes: int
    uploaded_bytes: int = 0
    chunks_completed: int = 0
    chunks_failed: int = 0
    chunks_retried: int = 0
    start_time: float = 0.0

    def __post_init__(self):
        if self.start_time == 0.0:
            self.start_time = time.time()

    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time

    @property
    def upload_speed(self) -> float:
        """Get upload speed in bytes/second."""
        if self.elapsed_time > 0:
            return self.uploaded_bytes / self.elapsed_time
        return 0.0

    @property
    def progress_percent(self) -> float:
        """Get progress as percentage."""
        if self.total_bytes > 0:
            return (self.uploaded_bytes / self.total_bytes) * 100
        return 0.0


class AdvancedTusClient:
    """Advanced TUS client with retry logic and error handling."""

    TUS_VERSION = "1.0.0"

    def __init__(
        self,
        url: str,
        chunk_size: Union[int, float] = 1024 * 1024,  # 1MB chunks
        max_workers: int = 1,  # Reserved for future use (TUS requires sequential uploads)  # noqa: E501
        max_retries: int = 3,  # Retry attempts per chunk
        retry_delay: float = 1.0,  # Delay between retries (seconds)
        checksum: bool = True,  # Enable checksum verification
    ):
        """Initialize advanced TUS client.

        Args:
            url: Base URL of TUS server
            chunk_size: Size of each chunk in bytes. Can be int or float.
            max_workers: Reserved for future (TUS requires sequential chunk uploads)
            max_retries: Maximum retry attempts for failed chunks
            retry_delay: Delay between retry attempts in seconds
            checksum: Enable SHA1 checksum verification
        """
        self.url = url.rstrip("/")
        self.chunk_size = int(chunk_size)
        self.max_workers = max_workers  # Not used - TUS requires sequential uploads
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.checksum = checksum
        self.stats_lock = Lock()
        self.logger = logging.getLogger(__name__)

    def upload_file_parallel(
        self,
        file_path: str,
        metadata: Optional[dict[str, str]] = None,
        progress_callback: Optional[Callable[[UploadStats], None]] = None,
    ) -> str:
        """Upload file with retry logic and progress tracking.

        Note: Despite the function name, chunks are uploaded sequentially as required
        by the TUS protocol. Each chunk must be uploaded at the correct offset.

        Args:
            file_path: Path to file to upload
            metadata: Optional metadata dictionary
            progress_callback: Optional callback for progress updates

        Returns:
            URL of uploaded file

        Raises:
            FileNotFoundError: If file doesn't exist
            Exception: On upload failure after all retries
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        stats = UploadStats(total_bytes=file_size)

        self.logger.info(f"Starting upload of {file_path} ({file_size} bytes)")
        self.logger.info(f"Chunk size: {self.chunk_size}, Max retries: {self.max_retries}")

        # Create upload
        upload_url = self._create_upload(file_size, metadata or {})
        self.logger.info(f"Upload created: {upload_url}")

        # Calculate chunks
        num_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
        self.logger.info(f"Split into {num_chunks} chunks")

        # Upload chunks sequentially (required by TUS protocol)
        for i in range(num_chunks):
            offset = i * self.chunk_size
            size = min(self.chunk_size, file_size - offset)

            try:
                self._upload_chunk_with_retry(file_path, upload_url, offset, size, stats)

                with self.stats_lock:
                    stats.uploaded_bytes += size
                    stats.chunks_completed += 1

                if progress_callback:
                    progress_callback(stats)

                self.logger.debug(f"Chunk {i + 1}/{num_chunks} completed (offset {offset})")

            except Exception as e:
                self.logger.error(f"Chunk at offset {offset} failed after all retries: {e}")
                with self.stats_lock:
                    stats.chunks_failed += 1
                raise

        self.logger.info(
            f"Upload completed in {stats.elapsed_time:.2f}s "
            f"({stats.upload_speed / 1024 / 1024:.2f} MB/s)"
        )
        return upload_url

    def _upload_chunk_with_retry(
        self,
        file_path: str,
        upload_url: str,
        offset: int,
        size: int,
        stats: UploadStats,
    ) -> None:
        """Upload a single chunk with retry logic.

        Args:
            file_path: Path to source file
            upload_url: Upload URL
            offset: Byte offset in file
            size: Chunk size in bytes
            stats: Upload statistics object

        Raises:
            Exception: If all retry attempts fail
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Read chunk from file
                with open(file_path, "rb") as f:
                    f.seek(offset)
                    data = f.read(size)

                # Verify chunk was read correctly
                if len(data) != size:
                    raise ValueError(f"Read {len(data)} bytes, expected {size} at offset {offset}")

                # Upload chunk
                self._upload_chunk(upload_url, offset, data)

                # Success!
                if attempt > 0:
                    with self.stats_lock:
                        stats.chunks_retried += 1
                    self.logger.info(
                        f"Chunk at offset {offset} succeeded after {attempt + 1} attempts"
                    )

                return

            except (HTTPError, URLError, OSError) as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2**attempt)  # Exponential backoff
                    self.logger.warning(
                        f"Chunk at offset {offset} failed "
                        f"(attempt {attempt + 1}/{self.max_retries}): {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                else:
                    self.logger.error(
                        f"Chunk at offset {offset} failed after {self.max_retries} attempts"
                    )

        # All retries failed
        raise Exception(
            f"Failed to upload chunk at offset {offset} after {self.max_retries} "
            f"attempts: {last_error}"
        )

    def _create_upload(self, file_size: int, metadata: dict[str, str]) -> str:
        """Create a new upload on the server."""
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Upload-Length": str(file_size),
        }

        if metadata:
            encoded_metadata = []
            for key, value in metadata.items():
                encoded_value = base64.b64encode(value.encode("utf-8")).decode("ascii")
                encoded_metadata.append(f"{key} {encoded_value}")
            headers["Upload-Metadata"] = ",".join(encoded_metadata)

        req = Request(self.url, headers=headers, method="POST")
        with urlopen(req) as response:
            location = response.headers.get("Location")
            # Handle relative URLs by joining with base URL
            return urljoin(self.url, location)

    def _upload_chunk(self, upload_url: str, offset: int, data: bytes) -> None:
        """Upload a single chunk."""
        headers = {
            "Tus-Resumable": self.TUS_VERSION,
            "Upload-Offset": str(offset),
            "Content-Type": "application/offset+octet-stream",
        }

        if self.checksum:
            checksum = hashlib.sha1(data).digest()
            headers["Upload-Checksum"] = f"sha1 {base64.b64encode(checksum).decode('ascii')}"

        req = Request(upload_url, data=data, headers=headers, method="PATCH")
        with urlopen(req):
            pass


def format_bytes(bytes_val: int) -> str:
    """Format bytes as human-readable string."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_val < 1024.0:
            return f"{bytes_val:.2f} {unit}"
        bytes_val /= 1024.0
    return f"{bytes_val:.2f} TB"


def progress_callback(stats: UploadStats) -> None:
    """Display detailed progress information."""
    speed_mb = stats.upload_speed / 1024 / 1024
    eta_seconds = (
        (stats.total_bytes - stats.uploaded_bytes) / stats.upload_speed
        if stats.upload_speed > 0
        else 0
    )

    bar_length = 40
    filled = int(bar_length * stats.uploaded_bytes / stats.total_bytes)
    bar = "█" * filled + "░" * (bar_length - filled)

    print(
        f"\r[{bar}] {stats.progress_percent:.1f}% | "
        f"{format_bytes(stats.uploaded_bytes)}/{format_bytes(stats.total_bytes)} | "
        f"{speed_mb:.2f} MB/s | "
        f"ETA: {eta_seconds:.0f}s | "
        f"Chunks: {stats.chunks_completed} OK, {stats.chunks_failed} Failed, "
        f"{stats.chunks_retried} Retried",
        end="",
    )

    if stats.uploaded_bytes >= stats.total_bytes:
        print()  # New line when complete


def main():
    """Run the advanced client example."""
    if len(sys.argv) < 3:
        print("Usage: python advanced_client_example.py <server_url> <file_path> [chunk_size_mb]")
        print()
        print("Examples:")
        print("  python advanced_client_example.py http://localhost:8080/files large_file.bin")
        print("  python advanced_client_example.py http://localhost:8080/files large_file.bin 2")
        print()
        print("Arguments:")
        print("  server_url    - TUS server URL")
        print("  file_path     - Path to file to upload")
        print("  chunk_size_mb - Chunk size in MB (default: 1)")
        sys.exit(1)

    server_url = sys.argv[1]
    file_path = sys.argv[2]
    chunk_size_mb = float(sys.argv[3]) if len(sys.argv) > 3 else 1

    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create client
    chunk_size = chunk_size_mb * 1024 * 1024
    client = AdvancedTusClient(
        server_url,
        chunk_size=chunk_size,
        max_retries=3,
        retry_delay=1.0,
        checksum=True,
    )

    # Upload file
    print("\nAdvanced TUS Client")
    print("=" * 80)
    print(f"File: {file_path}")
    print(f"Size: {format_bytes(os.path.getsize(file_path))}")
    print(f"Server: {server_url}")
    print(f"Chunk size: {chunk_size_mb} MB")
    print("Features: Retry logic, Checksum verification, Progress tracking")
    print("=" * 80)
    print()

    try:
        upload_url = client.upload_file_parallel(
            file_path,
            metadata={"filename": os.path.basename(file_path)},
            progress_callback=progress_callback,
        )

        print()
        print("✅ Upload completed successfully!")
        print(f"Upload URL: {upload_url}")

    except Exception as e:
        print()
        print(f"❌ Upload failed: {e}")
        logging.exception("Upload error")
        sys.exit(1)


if __name__ == "__main__":
    main()
