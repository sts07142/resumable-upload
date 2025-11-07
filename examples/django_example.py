#!/usr/bin/env python3
"""Django integration example for TUS server.

To use this example:
1. Install Django: pip install django
2. Create a Django project: django-admin startproject myproject
3. Add this view to your urls.py
4. Run: python manage.py runserver
"""

import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from resumable_upload import SQLiteStorage, TusServer

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# Create TUS server (should be created once, ideally in settings or app config)
storage = SQLiteStorage(db_path="uploads.db", upload_dir="uploads")
tus_server = TusServer(storage=storage, base_path="/files", max_size=100 * 1024 * 1024)


@csrf_exempt
@require_http_methods(["OPTIONS", "POST", "HEAD", "PATCH", "DELETE"])
def tus_upload_view(request, upload_id=None):
    """Handle TUS upload requests.

    Add to urls.py:
        from .views import tus_upload_view

        urlpatterns = [
            path('files', tus_upload_view, name='tus-create'),
            path('files/<str:upload_id>', tus_upload_view, name='tus-upload'),
        ]
    """
    # Get path
    path = request.path

    # Get headers as dict
    headers = {key: value for key, value in request.META.items() if key.startswith("HTTP_")}
    # Convert HTTP_X_Y format to X-Y format
    headers = {key[5:].replace("_", "-"): value for key, value in headers.items()}
    # Add Content-Type and Content-Length
    if request.META.get("CONTENT_TYPE"):
        headers["Content-Type"] = request.META["CONTENT_TYPE"]
    if request.META.get("CONTENT_LENGTH"):
        headers["Content-Length"] = request.META["CONTENT_LENGTH"]

    # Get body
    body = request.body

    # Handle request
    status, response_headers, response_body = tus_server.handle_request(
        request.method, path, headers, body
    )

    # Create response
    response = HttpResponse(response_body, status=status)
    for key, value in response_headers.items():
        response[key] = value

    return response


# Example standalone script for testing
if __name__ == "__main__":
    import django
    from django.conf import settings
    from django.core.servers.basehttp import WSGIRequestHandler, WSGIServer
    from django.core.wsgi import get_wsgi_application
    from django.urls import path

    # Configure Django settings
    settings.configure(
        DEBUG=True,
        SECRET_KEY="django-insecure-test-key-for-example-only",
        ROOT_URLCONF=__name__,
        ALLOWED_HOSTS=["*"],
        MIDDLEWARE=[
            "django.middleware.common.CommonMiddleware",
        ],
    )

    # Setup Django
    django.setup()

    # URL patterns
    urlpatterns = [
        path("files", tus_upload_view),
        path("files/<str:upload_id>", tus_upload_view),
    ]

    print("TUS Server with Django running on http://0.0.0.0:8000")
    print("Upload endpoint: http://0.0.0.0:8000/files")
    print("Press Ctrl+C to stop")

    # Get WSGI application
    application = get_wsgi_application()

    # Run development server directly
    server = WSGIServer(("0.0.0.0", 8000), WSGIRequestHandler)
    server.set_app(application)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server...")
        server.shutdown()
