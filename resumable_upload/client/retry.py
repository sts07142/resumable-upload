"""Advanced TUS client with retry logic and robust error handling."""

import logging
import time
from threading import Lock
from typing import Callable, Optional, Union
from urllib.error import HTTPError, URLError

from resumable_upload.client.base import TusClient
from resumable_upload.client.stats import UploadStats


class TusClientWithRetry(TusClient):
    """TUS client with automatic retry logic and detailed progress tracking.

    Extends the base TusClient with:
    - Automatic retry with exponential backoff
    - Detailed progress statistics via UploadStats
    - Comprehensive error handling and logging
    - Configurable retry parameters

    The TUS protocol requires sequential chunk uploads (not parallel) because
    each chunk must be uploaded at the correct offset. The server validates that
    the Upload-Offset header matches the current file position.

    Example:
        >>> client = TusClientWithRetry(
        ...     "http://localhost:8080/files", max_retries=3, retry_delay=1.0
        ... )
        >>> def progress(stats):
        ...     print(f"Progress: {stats.progress_percent:.1f}%")
        >>> url = client.upload_file("file.bin", progress_callback=progress)
    """

    def __init__(
        self,
        url: str,
        chunk_size: Union[int, float] = 1024 * 1024,  # 1MB chunks
        checksum: bool = True,  # Enable checksum verification
        max_retries: int = 3,  # Retry attempts per chunk
        retry_delay: float = 1.0,  # Initial delay between retries (seconds)
    ):
        """Initialize TUS client with retry capability.

        Args:
            url: Base URL of TUS server
            chunk_size: Size of each chunk in bytes (default: 1MB). Can be int or float.
            checksum: Enable SHA1 checksum verification (default: True)
            max_retries: Maximum retry attempts for failed chunks (default: 3)
            retry_delay: Base delay between retry attempts in seconds (default: 1.0)
        """
        super().__init__(url=url, chunk_size=chunk_size, checksum=checksum)
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.stats_lock = Lock()
        self.logger = logging.getLogger(__name__)

    def upload_file(
        self,
        file_path: str,
        metadata: Optional[dict[str, str]] = None,
        chunk_size: Optional[Union[int, float]] = None,
        progress_callback: Optional[Callable[[UploadStats], None]] = None,
    ) -> str:
        """Upload file with retry logic and progress tracking.

        Uploads chunks sequentially as required by the TUS protocol. Each chunk
        must be uploaded at the correct offset for data integrity.

        Args:
            file_path: Path to file to upload
            metadata: Optional metadata dictionary
            chunk_size: Optional override for chunk size. Can be int or float.
            progress_callback: Optional callback for progress updates with UploadStats

        Returns:
            URL of uploaded file

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If chunk_size is less than 1
            Exception: On upload failure after all retries
        """
        import os

        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        file_size = os.path.getsize(file_path)
        stats = UploadStats(total_bytes=file_size)

        # Use provided chunk_size or instance default, convert to int
        actual_chunk_size_raw = chunk_size if chunk_size is not None else self.chunk_size
        if actual_chunk_size_raw < 1:
            raise ValueError(f"chunk_size must be at least 1 byte, got {actual_chunk_size_raw}")
        actual_chunk_size = int(actual_chunk_size_raw)

        self.logger.info(f"Starting upload of {file_path} ({file_size} bytes)")
        self.logger.info(f"Chunk size: {actual_chunk_size}, Max retries: {self.max_retries}")

        # Create upload
        upload_url = self._create_upload(file_size, metadata or {})
        self.logger.info(f"Upload created: {upload_url}")

        # Calculate chunks
        num_chunks = (file_size + actual_chunk_size - 1) // actual_chunk_size
        self.logger.info(f"Split into {num_chunks} chunks")

        # Upload chunks sequentially (required by TUS protocol)
        for i in range(num_chunks):
            offset = i * actual_chunk_size
            size = min(actual_chunk_size, file_size - offset)

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
            f"Upload completed in {stats.elapsed_time:.2f}s ({stats.upload_speed_mbps:.2f} MB/s)"
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

                # Upload chunk using base class method
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
                    # Exponential backoff
                    delay = self.retry_delay * (2**attempt)
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
