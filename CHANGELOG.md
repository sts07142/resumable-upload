# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] - 2025-01-06

### Added

- Initial release of resumable-upload library
- TUS protocol v1.0.0 server implementation
- TUS protocol v1.0.0 client implementation
- TusClientWithRetry with automatic retry and exponential backoff
- SQLiteStorage backend for upload state management
- Comprehensive logging support (INFO, WARNING, ERROR, DEBUG levels)
- Custom exceptions: TusCommunicationError and TusUploadFailed
- File fingerprinting for cross-session resumability
- URL storage interface with FileURLStorage implementation
- Progress tracking with UploadStats dataclass
- Support for file streams alongside file paths
- Optional SHA1 checksum verification
- TLS certificate verification control
- Integration examples for Flask, FastAPI, and Django
- 70 comprehensive tests with 90%+ coverage
- Support for Python 3.9 through 3.14
- Zero runtime dependencies
- Complete documentation in English and Korean
- TUS protocol compliance documentation

### Features

- Sequential chunk uploads per TUS protocol requirements
- Automatic resume of interrupted uploads
- Configurable chunk size
- Metadata support with proper encoding
- Cross-platform compatibility
- PyPI-ready package structure

[0.0.1]: https://github.com/sts07142/resumable-upload/releases/tag/v0.0.1
