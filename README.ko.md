# Resumable Upload

[![Python Version](https://img.shields.io/pypi/pyversions/resumable-upload.svg)](https://pypi.org/project/resumable-upload/)
[![PyPI Version](https://img.shields.io/pypi/v/resumable-upload.svg)](https://pypi.org/project/resumable-upload/)
[![License](https://img.shields.io/pypi/l/resumable-upload.svg)](https://github.com/sts07142/resumable-upload/blob/main/LICENSE)

[English](README.md) | **한국어**

서버와 클라이언트를 위한 [TUS 재개 가능 업로드 프로토콜](https://tus.io/) v1.0.0의 Python 구현체로, 런타임 의존성이 없습니다.

## ✨ 특징

- 🚀 **의존성 없음**: Python 표준 라이브러리만 사용 (코어 기능에 외부 의존성 없음)
- 📦 **서버 & 클라이언트**: 양쪽 모두 완전한 구현
- 🔄 **재개 기능**: 중단된 업로드 자동 재개
- ✅ **데이터 무결성**: 선택적 SHA1 체크섬 검증
- 🔁 **재시도 로직**: 지수 백오프를 사용한 내장 자동 재시도
- 📊 **진행률 추적**: `UploadStats` 콜백으로 상세한 업로드 진행률 제공
- 🌐 **웹 프레임워크 지원**: Flask, FastAPI, Django 통합
- 🐍 **Python 3.9+**: Python 3.9부터 3.14까지 지원
- 🏪 **스토리지 백엔드**: SQLite 기반 스토리지 (커스텀 백엔드로 확장 가능)
- 🔐 **TLS 지원**: 인증서 검증 제어 및 mTLS 인증
- 📝 **URL 스토리지**: 세션 간 업로드 URL 유지
- 🎯 **TUS 프로토콜 준수**: TUS v1.0.0 코어 + creation, termination, checksum, expiration 확장 구현

## 📦 설치

### uv 사용 (권장)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
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

storage = SQLiteStorage(db_path="uploads.db", upload_dir="uploads")
tus_server = TusServer(storage=storage, base_path="/files")

class Handler(TusHTTPRequestHandler):
    pass

Handler.tus_server = tus_server
server = HTTPServer(("0.0.0.0", 8080), Handler)
print("서버가 http://localhost:8080 에서 실행 중입니다")
server.serve_forever()
```

### 기본 클라이언트

```python
from resumable_upload import TusClient, UploadStats

def progress(stats: UploadStats):
    print(f"진행률: {stats.progress_percent:.1f}% | "
          f"{stats.uploaded_bytes}/{stats.total_bytes} 바이트 | "
          f"속도: {stats.upload_speed_mbps:.2f} MB/s")

client = TusClient("http://localhost:8080/files")
upload_url = client.upload_file(
    "large_file.bin",
    metadata={"filename": "large_file.bin"},
    progress_callback=progress
)
print(f"업로드 완료: {upload_url}")
```

## 🔧 고급 사용법

자세한 가이드는 **[docs/advanced-usage.md](docs/advanced-usage.md)** 참조:

- 지수 백오프를 사용한 자동 재시도
- 중단된 업로드 재개 (세션 내 및 세션 간)
- `stop_at`을 사용한 부분 업로드
- `Uploader`를 통한 청크 단위 제어 + `stop_event`로 취소
- 예외 처리
- 웹 프레임워크 통합 (Flask, FastAPI, Django)

## 📚 API 참조

전체 API 문서는 **[docs/api-reference.md](docs/api-reference.md)** 참조.

### 빠른 참조

| 클래스 | 임포트 | 용도 |
|--------|--------|------|
| `TusClient` | `from resumable_upload import TusClient` | TUS 프로토콜로 파일 업로드 |
| `TusServer` | `from resumable_upload import TusServer` | TUS 업로드 서버 (프레임워크 무관) |
| `TusHTTPRequestHandler` | `from resumable_upload import TusHTTPRequestHandler` | Python 내장 `HTTPServer`용 핸들러 |
| `SQLiteStorage` | `from resumable_upload import SQLiteStorage` | SQLite + 파일시스템 스토리지 백엔드 |
| `FileURLStorage` | `from resumable_upload import FileURLStorage` | JSON 파일 기반 URL 영속성 |
| `Uploader` | `from resumable_upload.client.uploader import Uploader` | 저수준 청크 단위 제어 |

### 주요 파라미터

**`TusClient`**: `url`, `chunk_size` (기본값 1 MB), `checksum` (SHA1, 기본값 `True`), `max_retries` (기본값 3), `retry_delay` (기본값 1.0s, 지수 백오프 최대 60s), `timeout` (기본값 30s), `store_url` / `url_storage` (세션 간 재개), `verify_tls_cert`, `headers`

**`TusServer`**: `storage`, `base_path` (기본값 `/files`), `max_size`, `upload_expiry`, `cors_allow_origins`, `request_timeout` (기본값 30s — Slowloris 공격 방어)

**`SQLiteStorage`**: `db_path` (기본값 `uploads.db`), `upload_dir` (기본값 `uploads`) — 업로드별 락으로 스레드 안전; `fcntl.flock`으로 프로세스 안전

**`FileURLStorage`**: `storage_path` (기본값 `.tus_urls.json`) — `threading.Lock`으로 스레드 안전; `fcntl.flock`으로 프로세스 안전

## 🔍 TUS 프로토콜 준수

[TUS 프로토콜 v1.0.0](https://tus.io/protocols/resumable-upload.html) 구현. 전체 준수 현황: **[TUS_COMPLIANCE.md](TUS_COMPLIANCE.md)**.

### 확장 기능

| 확장 | 상태 |
|------|------|
| **core** | ✅ 구현됨 |
| **creation** | ✅ 구현됨 |
| **creation-with-upload** | ✅ 구현됨 |
| **termination** | ✅ 구현됨 |
| **checksum** | ✅ 구현됨 (SHA1) |
| **expiration** | ✅ 구현됨 |
| **concatenation** | ❌ 미구현 |

> **참고:** TUS `Upload-Checksum`은 스펙에 따라 **SHA1**을 사용합니다. 세션 간 재개를 위한 내부 파일 지문(fingerprint)은 **SHA-256**을 사용하며, TUS 프로토콜과는 무관합니다.

## 🧪 테스트

```bash
# uv가 없으면 설치
curl -LsSf https://astral.sh/uv/install.sh | sh

uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
make install

make test-minimal      # 최소 테스트 (웹 프레임워크 제외)
make test              # 전체 테스트
make lint              # 린팅
make format            # 코드 포맷팅
make test-all-versions # 모든 Python 버전 테스트 (3.9-3.14, tox 필요)
make ci                # 전체 CI 검사 (린팅 + 포맷팅 + 테스트)
```

## 📖 문서

- **English**: [README.md](README.md)
- **한국어 (Korean)**: [README.ko.md](README.ko.md)
- **고급 사용법**: [docs/advanced-usage.md](docs/advanced-usage.md)
- **전체 API 참조**: [docs/api-reference.md](docs/api-reference.md)
- **TUS 프로토콜 준수**: [TUS_COMPLIANCE.md](TUS_COMPLIANCE.md)

## 🤝 기여하기

기여를 환영합니다! 가이드라인은 [Contributing Guide](.github/CONTRIBUTING.md)를 확인해주세요.

## 📄 라이선스

MIT License - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.

## 🙏 감사의 말

이 라이브러리는 공식 [TUS Python client](https://github.com/tus/tus-py-client)에서 영감을 받았으며 [TUS 재개 가능 업로드 프로토콜](https://tus.io/)을 구현합니다.

## 📞 지원

- 📫 Issues: [GitHub Issues](https://github.com/sts07142/resumable-upload/issues)
- 📖 Documentation: [sts07142.github.io/resumable-upload](https://sts07142.github.io/resumable-upload/)
- 🌟 GitHub에서 스타를 눌러주세요!
