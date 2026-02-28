# TUS Protocol Compliance

Compliance status against the [TUS resumable upload protocol v1.0.0](https://tus.io/protocols/resumable-upload.html).

## Extensions

| Extension | Status | Notes |
|-----------|--------|-------|
| **core** | ✅ Implemented | POST / HEAD / PATCH, offset tracking, version negotiation |
| **creation** | ✅ Implemented | Upload creation via POST with `Upload-Length` |
| **creation-with-upload** | ✅ Implemented | Initial data in POST body (`Content-Type: application/offset+octet-stream`) |
| **termination** | ✅ Implemented | Upload deletion via DELETE |
| **checksum** | ✅ Implemented | SHA1 (`Upload-Checksum` header); `Tus-Checksum-Algorithm: sha1` advertised in OPTIONS |
| **expiration** | ✅ Implemented | `Upload-Expires` in POST / HEAD / PATCH responses; periodic server-side cleanup |
| **concatenation** | ❌ Not implemented | Combining parallel partial uploads |

## Version Negotiation

| Requirement | Status |
|-------------|--------|
| Client sends `Tus-Resumable` on all non-OPTIONS requests | ✅ |
| Server returns `Tus-Resumable` on all responses | ✅ |
| Server returns `412` on version mismatch | ✅ |
| Server skips version check for OPTIONS | ✅ |
| Server advertises supported versions in `Tus-Version` (OPTIONS) | ✅ |

## Core Protocol — Server

| Requirement | Status | Notes |
|-------------|--------|-------|
| POST creates new upload, returns `201` + `Location` | ✅ | |
| POST returns `400` on missing/invalid `Upload-Length` | ✅ | |
| POST returns `400` on negative `Upload-Length` | ✅ | |
| POST returns `413` when upload exceeds `Tus-Max-Size` | ✅ | |
| HEAD returns `200` with `Upload-Offset` + `Upload-Length` | ✅ | |
| HEAD includes `Cache-Control: no-store` | ✅ | |
| HEAD returns `404` for unknown upload | ✅ | |
| PATCH appends data, returns `204` + updated `Upload-Offset` | ✅ | |
| PATCH returns `415` on wrong `Content-Type` | ✅ | Must be `application/offset+octet-stream` |
| PATCH returns `409` on `Upload-Offset` mismatch | ✅ | |
| PATCH returns `400` on negative `Upload-Offset` | ✅ | |
| PATCH returns `400` if chunk would exceed `Upload-Length` | ✅ | |
| PATCH returns `460` on checksum mismatch | ✅ | Non-standard but widely used |
| PATCH returns `410` on expired upload | ✅ | |
| OPTIONS returns `204` with server capabilities | ✅ | |
| OPTIONS includes `Tus-Checksum-Algorithm` | ✅ | Reports `sha1` |
| DELETE removes upload, returns `204` | ✅ | |
| DELETE returns `404` for unknown upload | ✅ | |
| Malformed `Content-Length` header → `400` | ✅ | |
| Negative `Content-Length` → `400` | ✅ | |
| `Upload-Metadata` larger than 4 KB → `400` | ✅ | DoS protection |
| Invalid base64 in `Upload-Metadata` → `400` | ✅ | |
| Socket read timeout (Slowloris protection) | ✅ | `TusHTTPRequestHandler.setup()` applies `request_timeout` (default 30s) |

## Core Protocol — Client

| Requirement | Status | Notes |
|-------------|--------|-------|
| Sends `Tus-Resumable: 1.0.0` on all requests | ✅ | |
| POST to create upload with `Upload-Length` | ✅ | |
| HEAD to get current offset before resuming | ✅ | |
| PATCH with `Upload-Offset` and correct `Content-Type` | ✅ | |
| `Content-Length: 0` in DELETE request | ✅ | |
| Configurable timeout on all `urlopen()` calls | ✅ | Default 30s |
| Catches `URLError` (network-level) alongside `HTTPError` | ✅ | |
| Exponential backoff with cap (max 60s) | ✅ | |
| SHA1 checksum via `Upload-Checksum` header | ✅ | Optional |
| Cross-session URL persistence (fingerprint-based) | ✅ | `FileURLStorage` |
| Full-file fingerprint (not just first 64 KB) | ✅ | SHA-256 of entire content |
| `409` on concurrent offset conflict (atomic CAS) | ✅ | `UPDATE ... WHERE offset = ?`; returns `409` if row not updated |
| `409` received → HEAD re-sync before retry | ✅ | Client fetches current offset and re-seeks before retrying chunk |

## Not Implemented

| Feature | Notes |
|---------|-------|
| `concatenation` extension | Combining multiple partial uploads |
| `X-HTTP-Method-Override` | For environments blocking PATCH/DELETE |
| `Upload-Defer-Length` | Deferred length (part of creation extension) |
| Multiple TUS version support | Only `1.0.0` supported |

## Error Response Reference

| Status | Meaning | Trigger |
|--------|---------|---------|
| `400` | Bad Request | Missing/invalid header, negative offset, chunk overflow, oversized metadata |
| `404` | Not Found | Unknown upload ID |
| `409` | Conflict | `Upload-Offset` mismatch or concurrent write conflict |
| `410` | Gone | Upload has expired |
| `412` | Precondition Failed | Unsupported TUS version |
| `413` | Payload Too Large | Exceeds `Tus-Max-Size` |
| `415` | Unsupported Media Type | Wrong `Content-Type` in PATCH |
| `460` | Checksum Mismatch | SHA1 verification failed |

## References

- [TUS Protocol Specification v1.0.0](https://tus.io/protocols/resumable-upload.html)
- [TUS Protocol Extensions](https://tus.io/protocols/resumable-upload.html#protocol-extensions)
