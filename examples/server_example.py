#!/usr/bin/env python3
"""Example TUS server implementation."""

import logging
from http.server import HTTPServer

from resumable_upload import TusHTTPRequestHandler, TusServer
from resumable_upload.storage import SQLiteStorage


def main():
    """Run the TUS server."""
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    # Create storage backend
    storage = SQLiteStorage(db_path="uploads.db", upload_dir="uploads")

    # Create TUS server
    tus_server = TusServer(storage=storage, base_path="/files", max_size=100 * 1024 * 1024)

    # Create HTTP handler
    class Handler(TusHTTPRequestHandler):
        pass

    Handler.tus_server = tus_server

    # Start server
    host = "0.0.0.0"
    port = 8080
    server = HTTPServer((host, port), Handler)
    print(f"TUS Server running on http://{host}:{port}")
    print(f"Upload endpoint: http://{host}:{port}/files")
    print("Press Ctrl+C to stop")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()


if __name__ == "__main__":
    main()
