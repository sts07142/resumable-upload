#!/usr/bin/env python3
"""Example TUS uploader implementation for fine-grained upload control."""

import os
import sys
import time

from resumable_upload import TusClient, Uploader


def progress_callback(uploaded, total):
    """Display upload progress."""
    percent = (uploaded / total) * 100
    bar_length = 50
    filled = int(bar_length * uploaded / total)
    bar = "=" * filled + "-" * (bar_length - filled)
    print(f"\rProgress: [{bar}] {percent:.1f}% ({uploaded}/{total} bytes)", end="")
    if uploaded == total:
        print()


def main():
    """Run the uploader example."""
    if len(sys.argv) < 3:
        print("Usage: python uploader_example.py <server_url> <file_path> [upload_url]")
        print("Example: python uploader_example.py http://localhost:8080/files /path/to/file.bin")
        print(
            "Example with existing upload: python uploader_example.py "
            "http://localhost:8080/files /path/to/file.bin "
            "http://localhost:8080/files/abc123"
        )
        sys.exit(1)

    server_url = sys.argv[1]
    file_path = sys.argv[2]
    existing_upload_url = sys.argv[3] if len(sys.argv) > 3 else None

    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Example 1: Standalone Uploader usage
    print("\n=== Example 1: Standalone Uploader ===")
    if existing_upload_url:
        print(f"Using existing upload URL: {existing_upload_url}")
        uploader = Uploader(
            url=existing_upload_url,
            file_path=file_path,
            chunk_size=1024 * 1024,  # 1MB chunks
            headers={"Authorization": "Bearer token"},  # Optional headers
        )
    else:
        print("Creating new upload...")
        client = TusClient(server_url)
        uploader = client.create_uploader(
            file_path,
            metadata={"filename": os.path.basename(file_path)},
        )

    # Manual chunk-by-chunk upload
    print("Uploading chunks manually...")
    chunk_count = 0
    while uploader.upload_chunk():
        chunk_count += 1
        stats = uploader.stats
        print(
            f"Chunk {chunk_count}: {stats.uploaded_bytes}/{stats.total_bytes} bytes "
            f"({stats.progress_percent:.1f}%)"
        )
        # Simulate doing other work between chunks
        time.sleep(0.1)

    print(f"Upload complete! Total chunks: {chunk_count}")
    uploader.close()

    # Example 2: Using Uploader with context manager
    print("\n=== Example 2: Uploader with Context Manager ===")
    client = TusClient(server_url)
    with client.create_uploader(file_path) as uploader:
        # Upload entire file
        upload_url = uploader.upload(progress_callback=progress_callback)
        print(f"\nUpload complete: {upload_url}")

    # Example 3: Check upload status
    print("\n=== Example 3: Check Upload Status ===")
    client = TusClient(server_url)
    uploader = client.create_uploader(file_path)
    print(f"Initial offset: {uploader.offset}")
    print(f"File size: {uploader.file_size}")
    print(f"Is complete: {uploader.is_complete}")

    # Upload a few chunks
    for i in range(3):
        if uploader.upload_chunk():
            stats = uploader.stats
            print(f"After chunk {i + 1}: {stats.uploaded_bytes}/{stats.total_bytes} bytes")
        else:
            print("Upload complete!")
            break

    uploader.close()


if __name__ == "__main__":
    main()
