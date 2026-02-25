# Resumable Upload

[![Python Version](https://img.shields.io/pypi/pyversions/resumable-upload.svg)](https://pypi.org/project/resumable-upload/)
[![PyPI Version](https://img.shields.io/pypi/v/resumable-upload.svg)](https://pypi.org/project/resumable-upload/)
[![License](https://img.shields.io/pypi/l/resumable-upload.svg)](https://github.com/sts07142/resumable-upload/blob/main/LICENSE)

**English** | [한국어](README.ko.md)

Python 서버와 클라이언트를 위한 [TUS 재개 가능 업로드 프로토콜](https://tus.io/) v1.0.0의 구현체로, 런타임 의존성이 없습니다.

## ✨ 특징

- 🚀 **의존성 없음**: Python 표준 라이브러리만 사용 (코어 기능에 외부 의존성 없음)
- 📦 **서버 & 클라이언트**: 양쪽 모두 완전한 구현
- 🔄 **재개 기능**: 중단된 업로드 자동 재개
- ✅ **데이터 무결성**: 선택적 SHA1 체크섬 검증
- 🔁 **재시도 로직**: 지수 백오프를 사용한 내장 자동 재시도
- 📊 **진행률 추적**: 통계와 함께 상세한 업로드 진행률 콜백
- 🌐 **웹 프레임워크 지원**: Flask, FastAPI, Django 통합 예제
- 🐍 **Python 3.9+**: Python 3.9부터 3.14까지 지원
- 🏪 **스토리지 백엔드**: SQLite 기반 스토리지 (다른 백엔드로 확장 가능)
- 🔐 **TLS 지원**: 인증서 검증 제어 및 mTLS 인증
- 📝 **URL 스토리지**: 세션 간 업로드 URL 유지
- 🎯 **TUS 프로토콜 준수**: TUS v1.0.0 코어 프로토콜과 creation, termination, checksum 확장 구현

## 📦 설치

### uv 사용 (권장)

```bash
# uv가 설치되어 있지 않다면 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 패키지 설치
uv pip install resumable-upload
```

### pip 사용

```bash
pip install resumable-upload
```

## 🚀 빠른 시작

### 기본 서버

```python
from http.server import HTTPServer
from resumable_upload import TusServer, TusHTTPRequestHandler, SQLiteStorage

# 스토리지 백엔드 생성
storage = SQLiteStorage(db_path="uploads.db", upload_dir="uploads")

# TUS 서버 생성
tus_server = TusServer(storage=storage, base_path="/files")

# HTTP 핸들러 생성
class Handler(TusHTTPRequestHandler):
    pass

Handler.tus_server = tus_server

# 서버 시작
server = HTTPServer(("0.0.0.0", 8080), Handler)
print("서버가 http://localhost:8080 에서 실행 중입니다")
server.serve_forever()
```

### 기본 클라이언트

```python
from resumable_upload import TusClient

# 클라이언트 생성
client = TusClient("http://localhost:8080/files")

# 진행률 콜백과 함께 파일 업로드
from resumable_upload import UploadStats

def progress(stats: UploadStats):
    print(f"진행률: {stats.progress_percent:.1f}% | "
          f"{stats.uploaded_bytes}/{stats.total_bytes} 바이트 | "
          f"속도: {stats.upload_speed_mbps:.2f} MB/s")

upload_url = client.upload_file(
    "large_file.bin",
    metadata={"filename": "large_file.bin"},
    progress_callback=progress
)

print(f"업로드 완료: {upload_url}")
```

## 🔧 고급 사용법

### 자동 재시도가 있는 클라이언트

```python
from resumable_upload import TusClient

# 재시도 기능을 갖춘 클라이언트 생성 (기본적으로 활성화됨)
client = TusClient(
    "http://localhost:8080/files",
    chunk_size=1.5*1024*1024,  # 1.5MB 청크 (float 허용)
    max_retries=3,         # 최대 3회 재시도 (기본값: 3)
    retry_delay=1.0,       # 재시도 간 초기 지연 시간 (기본값: 1.0)
    checksum=True          # 체크섬 검증 활성화
)

# UploadStats를 사용한 진행률 추적과 함께 업로드
from resumable_upload import UploadStats

def progress_callback(stats: UploadStats):
    print(f"진행률: {stats.progress_percent:.1f}% | "
          f"속도: {stats.upload_speed_mbps:.2f} MB/s | "
          f"예상 시간: {stats.eta_seconds:.0f}초 | "
          f"청크: {stats.chunks_completed}/{stats.total_chunks} | "
          f"재시도: {stats.chunks_retried}")

upload_url = client.upload_file(
    "large_file.bin",
    metadata={"filename": "large_file.bin"},
    progress_callback=progress_callback
)
```

### 중단된 업로드 재개

```python
# 중단된 업로드 재개
upload_url = client.resume_upload("large_file.bin", upload_url)
```

### 세션 간 재개 가능성

```python
from resumable_upload import TusClient, FileURLStorage

# 세션 간 재개를 위한 URL 스토리지 활성화
storage = FileURLStorage(".tus_urls.json")
client = TusClient(
    "http://localhost:8080/files",
    store_url=True,
    url_storage=storage
)

# 중단 후 재시작 시 자동으로 재개됩니다
upload_url = client.upload_file("large_file.bin")
```

### 파일 스트림 사용

```python
# 경로 대신 파일 스트림에서 업로드
with open("file.bin", "rb") as fs:
    client = TusClient("http://localhost:8080/files")
    upload_url = client.upload_file(
        file_stream=fs,
        metadata={"filename": "file.bin"}
    )
```

### 예외 처리

```python
from resumable_upload import TusClient
from resumable_upload.exceptions import TusCommunicationError, TusUploadFailed

client = TusClient("http://localhost:8080/files")

try:
    upload_url = client.upload_file("file.bin")
except TusCommunicationError as e:
    print(f"통신 오류: {e.message}, 상태: {e.status_code}")
except TusUploadFailed as e:
    print(f"업로드 실패: {e.message}")
```

## 🌐 웹 프레임워크 통합

### Flask

```python
from flask import Flask, request, make_response
from resumable_upload import TusServer, SQLiteStorage

app = Flask(__name__)
tus_server = TusServer(storage=SQLiteStorage())

@app.route('/files', methods=['OPTIONS', 'POST'])
@app.route('/files/<upload_id>', methods=['HEAD', 'PATCH', 'DELETE'])
def handle_upload(upload_id=None):
    status, headers, body = tus_server.handle_request(
        request.method, request.path, dict(request.headers), request.get_data()
    )
    response = make_response(body, status)
    for key, value in headers.items():
        response.headers[key] = value
    return response
```

### FastAPI

```python
from fastapi import FastAPI, Request, Response
from resumable_upload import TusServer, SQLiteStorage

app = FastAPI()
tus_server = TusServer(storage=SQLiteStorage())

@app.post("/files")
@app.head("/files/{upload_id}")
@app.patch("/files/{upload_id}")
@app.delete("/files/{upload_id}")
async def handle_upload(request: Request):
    body = await request.body()
    status, headers, response_body = tus_server.handle_request(
        request.method, request.url.path, dict(request.headers), body
    )
    return Response(content=response_body, status_code=status, headers=headers)
```

### Django

```python
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from resumable_upload import TusServer, SQLiteStorage

tus_server = TusServer(storage=SQLiteStorage())

@csrf_exempt
def tus_upload_view(request, upload_id=None):
    headers = {key[5:].replace('_', '-'): value
               for key, value in request.META.items() if key.startswith('HTTP_')}
    status, response_headers, response_body = tus_server.handle_request(
        request.method, request.path, headers, request.body
    )
    response = HttpResponse(response_body, status=status)
    for key, value in response_headers.items():
        response[key] = value
    return response
```

## 📚 API 참조

### TusClient

파일 업로드를 위한 메인 클라이언트 클래스입니다.

**매개변수:**

- `url` (str): TUS 서버 기본 URL
- `chunk_size` (int): 각 업로드 청크의 크기(바이트) (기본값: 1MB)
- `checksum` (bool): SHA1 체크섬 검증 활성화 (기본값: True)
- `store_url` (bool): 재개를 위한 업로드 URL 저장 (기본값: False)
- `url_storage` (URLStorage): URL 스토리지 백엔드 (기본값: FileURLStorage)
- `verify_tls_cert` (bool): TLS 인증서 검증 (기본값: True)
- `metadata_encoding` (str): 메타데이터 인코딩 (기본값: "utf-8")
- `headers` (dict): 모든 요청에 포함할 커스텀 헤더 (기본값: {})
- `max_retries` (int): 청크당 최대 재시도 횟수 (기본값: 3)
- `retry_delay` (float): 재시도 간 기본 지연 시간(초) (기본값: 1.0)

**메서드:**

- `upload_file(file_path=None, file_stream=None, metadata={}, progress_callback=None, stop_at=None)`: 파일 업로드
  - `progress_callback`: `UploadStats` 객체를 받는 콜백 함수
- `resume_upload(file_path, upload_url, progress_callback=None)`: 중단된 업로드 재개
  - `progress_callback`: `UploadStats` 객체를 받는 콜백 함수
- `delete_upload(upload_url)`: 업로드 삭제
- `get_upload_info(upload_url)`: 업로드 정보 조회 (offset, length, complete, metadata)
- `get_metadata(upload_url)`: 업로드 메타데이터 조회
- `get_server_info()`: 서버 기능 및 정보 조회
- `update_headers(headers)`: 런타임에 커스텀 헤더 업데이트
- `get_headers()`: 현재 커스텀 헤더 가져오기
- `create_uploader(file_path=None, file_stream=None, upload_url=None, metadata={}, chunk_size=None)`: Uploader 인스턴스 생성

### TusClient 재시도 설정

`TusClient`는 지수 백오프를 사용한 내장 재시도 기능을 포함합니다.

**재시도 매개변수:**

- `max_retries` (int): 청크당 최대 재시도 횟수 (기본값: 3)
- `retry_delay` (float): 재시도 간 기본 지연 시간(초) (기본값: 1.0)
  - 지수 백오프 사용: delay = retry_delay * (2^attempt)
- 재시도를 비활성화하려면 `max_retries=0` 설정

### TusServer

TUS 프로토콜의 서버 구현입니다.

**매개변수:**

- `storage` (Storage): 업로드를 관리하기 위한 스토리지 백엔드
- `base_path` (str): TUS 엔드포인트의 기본 경로 (기본값: "/files")
- `max_size` (int): 최대 업로드 크기(바이트) (기본값: None)

**메서드:**

- `handle_request(method, path, headers, body)`: TUS 프로토콜 요청 처리

### SQLiteStorage

SQLite 기반 스토리지 백엔드입니다.

**매개변수:**

- `db_path` (str): SQLite 데이터베이스 파일 경로 (기본값: "uploads.db")
- `upload_dir` (str): 업로드 파일을 저장할 디렉토리 (기본값: "uploads")

## 🔍 TUS 프로토콜 준수

이 라이브러리는 [TUS 프로토콜 v1.0.0](https://tus.io/protocols/resumable-upload.html)을 구현합니다.

### 확장 기능

| 확장 | 상태 | 비고 |
|------|------|------|
| **core** | ✅ 구현됨 | POST / HEAD / PATCH, 오프셋 추적, 버전 협상 |
| **creation** | ✅ 구현됨 | `Upload-Length` 포함 POST로 업로드 생성 |
| **creation-with-upload** | ✅ 구현됨 | POST 본문에 초기 데이터 포함 |
| **termination** | ✅ 구현됨 | DELETE로 업로드 삭제 |
| **checksum** | ✅ 구현됨 | SHA1 (`Upload-Checksum` 헤더); OPTIONS에서 `Tus-Checksum-Algorithm: sha1` 광고 |
| **expiration** | ✅ 구현됨 | POST / HEAD / PATCH 응답에 `Upload-Expires`; 서버 측 주기적 정리 |
| **concatenation** | ❌ 미구현 | 병렬 부분 업로드 결합 |

### 프로토콜 세부 사항

| 요구 사항 | 상태 | 비고 |
|-----------|------|------|
| 모든 응답에 `Tus-Resumable` 헤더 포함 | ✅ | |
| 버전 불일치 시 `412` 반환 | ✅ | |
| PATCH의 잘못된 `Content-Type` → `415` | ✅ | |
| `Upload-Offset` 불일치 → `409` | ✅ | |
| 만료된 업로드 접근 → `410` | ✅ | |
| HEAD 응답에 `Cache-Control: no-store` | ✅ | |
| POST / HEAD / PATCH 응답에 `Upload-Expires` | ✅ | 만료 설정 시 |
| OPTIONS에 `Tus-Checksum-Algorithm` | ✅ | `sha1` 보고 |
| 클라이언트 DELETE에 `Content-Length: 0` | ✅ | |
| 잘못된 `Content-Length` → `400` | ✅ | |
| 청크 초과 → `400` | ✅ | 선언된 `Upload-Length` 초과 방지 |
| `X-HTTP-Method-Override` | ❌ 미구현 | PATCH/DELETE 차단 환경용 |
| `Upload-Defer-Length` (지연 길이) | ❌ 미구현 | creation 확장의 일부 |

### 순차적 업로드 요구사항

**중요:** TUS 프로토콜은 청크를 **순차적으로** 업로드해야 하며, 병렬로 업로드할 수 없습니다.

1. **오프셋 검증**: 각 청크는 올바른 바이트 오프셋에 업로드되어야 합니다
2. **데이터 무결성**: 경쟁 조건으로 인한 데이터 손상을 방지합니다
3. **재개 기능**: 수신된 바이트 추적을 간단하고 신뢰할 수 있게 만듭니다
4. **프로토콜 준수**: TUS 사양은 `Upload-Offset`이 현재 위치와 일치해야 한다고 요구합니다

```python
# ❌ 병렬 업로드는 충돌을 일으킵니다:
# 청크 1 (오프셋 0)    → 성공
# 청크 3 (오프셋 2048) → 실패 (409: 예상 오프셋 1024)
# 청크 2 (오프셋 1024) → 실패 (409: 오프셋 불일치)

# ✅ 순차적 업로드는 올바르게 작동합니다:
# 청크 1 (오프셋 0)    → 성공 (오프셋 이제 1024)
# 청크 2 (오프셋 1024) → 성공 (오프셋 이제 2048)
# 청크 3 (오프셋 2048) → 성공 (오프셋 이제 3072)
```

## 🧪 테스트

### uv 사용 (권장)

```bash
# uv가 설치되어 있지 않다면 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

# 가상 환경 생성 및 의존성 설치
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 모든 의존성 설치 (dev 및 test 포함)
make install

# 최소 테스트 실행 (웹 프레임워크 제외)
make test-minimal

# 모든 테스트 실행 (웹 프레임워크 포함)
make test

# 또는 Makefile 사용 (편리함)
make lint              # 린팅 실행
make format            # 코드 포맷팅
make test-minimal      # 최소 테스트 실행
make test              # 모든 테스트 실행
make test-all-versions # 모든 Python 버전에서 테스트 (3.9-3.14) - tox 필요
make ci                # 전체 CI 검사 실행 (린팅 + 포맷팅 + 테스트)
```

## 📖 문서

- **English**: [README.md](README.md)
- **한국어 (Korean)**: [README.ko.md](README.ko.md)
- **TUS Protocol Compliance**: [TUS_COMPLIANCE.md](TUS_COMPLIANCE.md)

## 🤝 기여하기

기여를 환영합니다! 가이드라인은 [Contributing Guide](.github/CONTRIBUTING.md)를 확인해주세요.

## 📄 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 🙏 감사의 말

이 라이브러리는 공식 [TUS Python client](https://github.com/tus/tus-py-client)에서 영감을 받았으며 [TUS 재개 가능 업로드 프로토콜](https://tus.io/)을 구현합니다.

## 📞 지원

- 📫 Issues: [GitHub Issues](https://github.com/sts07142/resumable-upload/issues)
- 📖 Documentation: [GitHub README](https://github.com/sts07142/resumable-upload#readme)
- 🌟 GitHub에서 스타를 눌러주세요!
