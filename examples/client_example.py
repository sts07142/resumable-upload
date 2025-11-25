#!/usr/bin/env python3
"""Example TUS client implementation."""

import json
import os
import sys

from resumable_upload import TusClient, UploadStats


def progress_callback(stats: UploadStats):
    """Display upload progress."""
    percent = (stats.uploaded_bytes / stats.total_bytes) * 100
    bar_length = 50
    filled = int(bar_length * stats.uploaded_bytes / stats.total_bytes)
    bar = "=" * filled + "-" * (bar_length - filled)
    print(
        f"\rProgress: [{bar}] {percent:.1f}% ({stats.uploaded_bytes}/{stats.total_bytes} bytes)",
        end="",
    )

    if stats.uploaded_bytes == stats.total_bytes:
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
    print(f"Getting server information for {server_url}")
    try:
        server_info = client.get_server_info()
        print(f"Server TUS Version: {server_info['version']}")
        print(f"Supported Extensions: {server_info['extensions']}")
        if server_info["max_size"]:
            print(f"Max Upload Size: {server_info['max_size']} bytes")
    except Exception as e:
        print(f"Warning: Could not get server info: {e}")

    print("--------------------------------")

    # Upload file
    print(f"Uploading {file_path} to {server_url}")
    upload_url = None
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

    # If upload failed, skip remaining examples
    if upload_url is None:
        print("\nSkipping remaining examples due to upload failure.")
        sys.exit(1)

    print("--------------------------------")

    # Example: Get upload information
    print(f"Getting upload information for {upload_url}")
    try:
        upload_info = client.get_upload_info(upload_url)
        print(f"Upload offset: {upload_info['offset']}/{upload_info['length']}")
        print(f"Upload complete: {upload_info['complete']}")
        print(f"Upload metadata: {upload_info['metadata']}")
    except Exception as e:
        print(f"Getting upload information failed: {e}")

    print("--------------------------------")

    # Example: Get metadata only
    print(f"Getting metadata for {upload_url}")
    try:
        metadata = client.get_metadata(upload_url)
        print(f"Metadata: {metadata}")
    except Exception as e:
        print(f"Getting metadata failed: {e}")

    print("--------------------------------")

    # Example: Use Uploader for fine-grained control
    print(f"Using Uploader for fine-grained control for {upload_url}")
    try:
        print("\n=== Example: Using Uploader ===")
        uploader = client.create_uploader(file_path, upload_url=upload_url)
        print(f"Uploader offset: {uploader.offset}, file size: {uploader.file_size}")
        print(f"Is complete: {uploader.is_complete}")
        uploader.close()

    except Exception as e:
        print(f"Upload failed: {e}")

    print("--------------------------------")


if __name__ == "__main__":
    main()
