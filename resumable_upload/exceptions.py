"""
Global resumable_upload exception classes.

Based on tusclient exceptions for compatibility with TUS protocol error handling.
"""


class TusCommunicationError(Exception):
    """
    Exception raised when communication with TUS server behaves unexpectedly.

    Attributes:
        message (str): Main message of the exception
        status_code (int): HTTP status code of response indicating an error
        response_content (bytes): Content of response indicating an error
    """

    def __init__(self, message, status_code=None, response_content=None):
        default_message = f"Communication with TUS server failed with status {status_code}"
        message = message or default_message
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.response_content = response_content


class TusUploadFailed(TusCommunicationError):
    """Exception raised when an attempted upload fails."""

    pass
