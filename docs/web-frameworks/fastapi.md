# FastAPI

```python
from fastapi import FastAPI, Request, Response
from resumable_upload import TusServer, SQLiteStorage

app = FastAPI()
tus_server = TusServer(storage=SQLiteStorage())

@app.api_route("/files", methods=["OPTIONS", "POST"])
@app.api_route("/files/{upload_id}", methods=["HEAD", "PATCH", "DELETE"])
async def handle_upload(request: Request):
    body = await request.body()
    status, headers, response_body = tus_server.handle_request(
        request.method, request.url.path, dict(request.headers), body
    )
    return Response(content=response_body, status_code=status, headers=headers)
```

## Running

=== "uv"

    ```bash
    uv add fastapi uvicorn resumable-upload
    uvicorn main:app --reload
    ```

=== "pip"

    ```bash
    pip install fastapi uvicorn resumable-upload
    uvicorn main:app --reload
    ```

See `examples/fastapi_server.py` for a complete working example.
