# TUS Protocol Compliance

This document explains how this library implements the TUS resumable upload protocol and its version handling.

## TUS Protocol Version

This library implements **TUS Protocol version 1.0.0** as specified at:
https://tus.io/protocols/resumable-upload.html

## Version Handling

### How TUS Version Negotiation Works

According to the official TUS specification:

1. **Client Requirements:**
   - Client MUST include `Tus-Resumable` header in ALL requests (except OPTIONS)
   - The header value indicates the protocol version the client wants to use
   - Example: `Tus-Resumable: 1.0.0`

2. **Server Requirements:**
   - Server MUST include `Tus-Resumable` header in ALL responses
   - Server checks if it supports the version requested by client
   - If supported: proceed with the request
   - If NOT supported: return `412 Precondition Failed`

3. **Version Discovery (OPTIONS):**
   - Server returns `Tus-Version` header listing all supported versions
   - Example: `Tus-Version: 1.0.0,0.2.2,0.2.1`

### Our Implementation

**Server (`TusServer`):**
- Supports only TUS version `1.0.0`
- Checks `Tus-Resumable` header on all non-OPTIONS requests
- Returns `412 Precondition Failed` if version is not exactly `1.0.0`
- Returns `Tus-Version: 1.0.0` in OPTIONS response

**Client (`TusClient`):**
- Uses TUS version `1.0.0`
- Sends `Tus-Resumable: 1.0.0` header with all requests
- Compatible with any TUS 1.0.0 compliant server

### Why Strict Version Checking?

**This is correct behavior according to TUS specification!**

The specification requires:
- Servers check for EXACT version match
- Servers are NOT required to support multiple versions
- Servers MUST return 412 if version is not supported

Our implementation:
- ✅ Only supports version 1.0.0 (valid choice)
- ✅ Checks for exact match (required)
- ✅ Returns proper error code 412 (required)
- ✅ Includes version in error response (required)

### Working Together

The client and server in this library work together because:
1. Both use the same TUS version: `1.0.0`
2. Client sends: `Tus-Resumable: 1.0.0`
3. Server accepts: `1.0.0`
4. Version match → Request proceeds

### Using with Other TUS Implementations

**Server Compatibility:**
- Any TUS 1.0.0 compliant client can use our server
- Clients using other versions (e.g., 0.2.2) will receive 412 error

**Client Compatibility:**
- Our client works with any TUS 1.0.0 compliant server
- Servers supporting only other versions will reject our client

## Supported Features

### Core Protocol
- ✅ Upload creation (POST)
- ✅ Upload status check (HEAD)
- ✅ Data upload (PATCH)
- ✅ Offset tracking
- ✅ Resumable uploads

### Extensions
- ✅ **creation**: Upload creation via POST
- ✅ **termination**: Upload deletion via DELETE
- ✅ **checksum**: SHA1 checksum verification (optional)

### Not Implemented
- ❌ **concatenation**: Combining multiple uploads
- ❌ **expiration**: Automatic upload expiry
- ❌ Multiple protocol versions support

## Protocol Headers

### Required Headers

**Client → Server:**
```
Tus-Resumable: 1.0.0           (All requests except OPTIONS)
Upload-Length: 1024             (POST - create upload)
Upload-Offset: 0                (PATCH - append data)
Content-Type: application/offset+octet-stream  (PATCH)
```

**Server → Client:**
```
Tus-Resumable: 1.0.0           (All responses)
Tus-Version: 1.0.0             (OPTIONS response)
Tus-Extension: creation,termination,checksum  (OPTIONS)
Upload-Offset: 512             (HEAD, PATCH responses)
Location: /files/{id}          (POST response)
```

### Optional Headers

**Client → Server:**
```
Upload-Metadata: filename dGVzdC50eHQ=    (POST - base64 encoded)
Upload-Checksum: sha1 {base64-hash}       (PATCH - verify data)
```

**Server → Client:**
```
Tus-Max-Size: 104857600        (OPTIONS - if size limit configured)
Upload-Length: 1024             (HEAD - total file size)
```

## Error Responses

| Status | Meaning | Reason |
|--------|---------|--------|
| 412 | Precondition Failed | Wrong TUS version |
| 400 | Bad Request | Missing required header |
| 404 | Not Found | Upload ID doesn't exist |
| 409 | Conflict | Upload offset mismatch |
| 413 | Payload Too Large | File exceeds max size |
| 460 | Checksum Mismatch | Data integrity check failed |

## References

- **TUS Protocol Specification**: https://tus.io/protocols/resumable-upload.html
- **TUS Core Protocol**: https://tus.io/protocols/resumable-upload.html#core-protocol
- **Version Negotiation**: https://tus.io/protocols/resumable-upload.html#version-negotiation
- **TUS Extensions**: https://tus.io/protocols/resumable-upload.html#protocol-extensions

## FAQ

**Q: Why does the server reject clients with different TUS versions?**
A: This is required by the TUS specification. Servers must check for version compatibility and return 412 if the version is not supported.

**Q: Can I use this client with other TUS servers?**
A: Yes, as long as the server supports TUS protocol version 1.0.0.

**Q: Can other clients use this server?**
A: Yes, any TUS 1.0.0 compliant client will work with this server.

**Q: Why not support multiple TUS versions?**
A: Supporting multiple versions adds complexity. TUS 1.0.0 is the stable version and widely supported. Adding more versions is possible but not necessary for most use cases.

**Q: Is the version check too strict?**
A: No, this is exactly how TUS is designed to work. The specification explicitly requires exact version matching.
