#!/usr/bin/env python3
"""Flask integration example for TUS server."""

import logging

from flask import Flask, make_response, request

from resumable_upload import SQLiteStorage, TusServer

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Create Flask app
app = Flask(__name__)

# Create TUS server
storage = SQLiteStorage(db_path="uploads.db", upload_dir="uploads")
tus_server = TusServer(storage=storage, base_path="/files", max_size=100 * 1024 * 1024)


@app.route("/files", methods=["OPTIONS", "POST"])
@app.route("/files/<upload_id>", methods=["HEAD", "PATCH", "DELETE"])
def handle_upload(upload_id=None):
    """Handle TUS upload requests."""
    # Get path
    path = request.path

    # Get headers as dict
    headers = dict(request.headers)

    # Get body
    body = request.get_data()

    # Handle request
    status, response_headers, response_body = tus_server.handle_request(
        request.method, path, headers, body
    )

    # Create response
    response = make_response(response_body, status)
    for key, value in response_headers.items():
        response.headers[key] = value

    return response


if __name__ == "__main__":
    print("TUS Server with Flask running on http://0.0.0.0:5000")
    print("Upload endpoint: http://0.0.0.0:5000/files")
    print("Press Ctrl+C to stop")
    app.run(host="0.0.0.0", port=5000, debug=False)
