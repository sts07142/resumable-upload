#!/usr/bin/env python3
"""Example TUS client implementation."""

import json
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
        print("Usage: python client_example.py <server_url> <file_path> <headers>")
        print(
            "Example: python client_example.py http://localhost:8080/files /path/to/file.bin "
            '{"Authorization": "Bearer your-token-here"}'
        )
        sys.exit(1)

    server_url = sys.argv[1]
    file_path = sys.argv[2]
    headers = json.loads(sys.argv[3]) if len(sys.argv) > 3 else {}

    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    # Create client with custom headers (e.g., for authentication)
    # Example: Add Authorization header or custom API key
    custom_headers = headers
    client = TusClient(
        server_url,
        chunk_size=1024 * 1024,  # 1MB chunks
        headers=custom_headers,  # Custom headers will be included in all requests
    )

    # Example: Get server information
    try:
        server_info = client.get_server_info()
        print(f"Server TUS Version: {server_info['version']}")
        print(f"Supported Extensions: {server_info['extensions']}")
        if server_info["max_size"]:
            print(f"Max Upload Size: {server_info['max_size']} bytes")
    except Exception as e:
        print(f"Warning: Could not get server info: {e}")

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

        # Example: Get upload information
        upload_info = client.get_upload_info(upload_url)
        print(f"Upload offset: {upload_info['offset']}/{upload_info['length']}")
        print(f"Upload complete: {upload_info['complete']}")
        print(f"Upload metadata: {upload_info['metadata']}")

        # Example: Get metadata only
        metadata = client.get_metadata(upload_url)
        print(f"Metadata: {metadata}")

    except Exception as e:
        print(f"Upload failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
