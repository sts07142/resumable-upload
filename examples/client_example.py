#!/usr/bin/env python3
"""Example TUS client implementation."""

import os
import sys

from resumable_upload import TusClient


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
    """Run the client example."""
    if len(sys.argv) < 3:
        print("Usage: python client_example.py <server_url> <file_path>")
        print("Example: python client_example.py http://localhost:8080/files /path/to/file.bin")
        sys.exit(1)

    server_url = sys.argv[1]
    file_path = sys.argv[2]

    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Create client
    client = TusClient(server_url, chunk_size=1024 * 1024)  # 1MB chunks

    # Upload file
    print(f"Uploading {file_path} to {server_url}")
    try:
        upload_url = client.upload_file(
            file_path,
            metadata={"filename": os.path.basename(file_path)},
            progress_callback=progress_callback,
        )
        print("Upload complete!")
        print(f"Upload URL: {upload_url}")
    except Exception as e:
        print(f"Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
