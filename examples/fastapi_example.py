#!/usr/bin/env python3
"""FastAPI integration example for TUS server."""

import logging

import uvicorn
from fastapi import FastAPI, Request, Response

from resumable_upload import SQLiteStorage, TusServer

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Create FastAPI app
app = FastAPI(title="TUS Upload Server")

# Create TUS server
storage = SQLiteStorage(db_path="uploads.db", upload_dir="uploads")
tus_server = TusServer(storage=storage, base_path="/files", max_size=100 * 1024 * 1024)


@app.options("/files")
@app.post("/files")
async def create_upload(request: Request):
    """Handle upload creation."""
    return await handle_tus_request(request)


@app.head("/files/{upload_id}")
@app.patch("/files/{upload_id}")
@app.delete("/files/{upload_id}")
async def handle_upload(upload_id: str, request: Request):
    """Handle upload operations."""
    return await handle_tus_request(request)


async def handle_tus_request(request: Request):
    """Process TUS request."""
    # Get path
    path = request.url.path

    # Get headers as dict
    headers = dict(request.headers)

    # Get body
    body = await request.body()

    # Handle request
    status, response_headers, response_body = tus_server.handle_request(
        request.method, path, headers, body
    )

    # Create response
    return Response(content=response_body, status_code=status, headers=response_headers)


if __name__ == "__main__":
    print("TUS Server with FastAPI running on http://0.0.0.0:8000")
    print("Upload endpoint: http://0.0.0.0:8000/files")
    print("API docs: http://0.0.0.0:8000/docs")
    print("Press Ctrl+C to stop")
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
