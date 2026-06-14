# DECISIONS

doongle-ai 설계 결정 로그. 결정이 생기거나 바뀔 때마다 **아래에 시간순으로 추가**한다.
(언제 바뀌었나는 git 히스토리가, 왜 바뀌었나는 이 파일이 기록한다.)

---

## 2026-06-14 — 동기 워커 (async 아님)
- 결정: kafka-python 동기 consumer 루프 + 동기 SQLAlchemy로 구현한다.
- 이유: 워커의 본업은 GPU 추론(연산 중심, 순차 처리)이라 async의 I/O 동시성 이점이 없다. consumer 루프가 동기라 DB도 동기로 맞추면 코드가 단순하고 일관된다. (api는 FastAPI라 async가 맞았지만 워커는 성격이 반대.)

## 2026-06-14 — 처리량은 수평 확장(scale-out)으로
- 결정: 워커 한 개는 단순하게(한 번에 하나 처리), 처리량은 replica를 늘려 해결. 모든 워커가 같은 group_id로 컨슈머 그룹을 이룬다.
- 이유: 같은 group_id면 Kafka가 메시지를 워커들에 분배(중복 없이)한다. 워커 코드를 복잡하게 만들지 않고 Deployment replicas로 확장 가능. Phase 2 분산 추론/HPA 서사와 연결. (스케일 시 토픽 파티션 수도 워커 수에 맞춰 고려 — 배포 단계.)
- group_id는 consumer(워커)가 정하는 개념. producer(api)는 무관.

## 2026-06-14 — 메시지는 경로(image_path), 이미지는 storage에서 load
- 결정: 워커는 메시지의 image_path로 StorageBackend.load()를 통해 이미지를 읽는다. (api가 보낸 경량 메시지 {job_id, image_path} 그대로)
- 이유: api와 동일한 스토리지 추상화 계약. 로컬은 LocalStorage(같은 ./uploads 파일 읽기), 배포는 MinioStorage(네트워크). STORAGE_BACKEND 환경변수로 전환, 워커 코드는 불변.

## 2026-06-14 — 결과는 PostgreSQL jobs 테이블에 update
- 결정: 추론 결과를 api와 같은 PostgreSQL jobs 테이블에 status=done, result=라벨로 update한다. 워커는 jobs를 최소 컬럼(job_id, status, result)으로 매핑.
- 이유: api가 pending으로 insert한 job을 워커가 done으로 갱신 = 폴링 화면이 결과를 보게 되는 연결고리. 모델 정의는 레포가 분리돼 최소 재매핑(공유 패키지는 현 단계 오버엔지니어링).

## 2026-06-14 — (단계1) 설정은 config.py 한 곳에서 로드, python-dotenv 추가, 비밀값 로그 마스킹
- 결정: 환경변수 읽기를 `config.py`의 `load_settings()` 한 곳으로 모은다(frozen dataclass `Settings`). 로컬 편의를 위해 `python-dotenv`를 의존성에 추가하되, 미설치 시 조용히 무시하고 순수 환경변수만 쓴다. DATABASE_URL은 `required`로 강제하고, 로그 출력 시 비밀번호를 `***`로 가린다(`redacted()`).
- 이유: 설정 분기 로직이 흩어지지 않게 한 곳에 모은다. `.env.example`을 step1 범위로 두었으니 로컬에서 .env를 자동 로드할 수단(dotenv)이 필요하다. 단, 배포(k8s ConfigMap/Secret)에는 .env가 없으므로 dotenv는 optional import로 둔다. DB URL은 비밀값이라 로그에 평문으로 남기지 않는다.
- 비고: 의존성 목록(TASKS step1)에 없던 python-dotenv를 추가한 것이 이번 결정의 핵심 변경점.

## 2026-06-14 — (단계2) image_path는 base_path 기준 상대경로 키로 해석, 경로 탈출 방어
- 결정: `StorageBackend.load(image_path) -> bytes` 계약. `LocalStorage`는 image_path를 `LOCAL_STORAGE_PATH` 기준 상대경로(스토리지 키)로 보고 합쳐 읽는다. image_path가 절대경로면 그대로 사용. 상대경로 합성 시 base_path를 벗어나면(`../`) `ValueError`로 막는다. `MinioStorage`는 생성 시 `NotImplementedError`(자리만). 분기는 `get_storage(settings)` 팩토리가 `STORAGE_BACKEND`로 한다.
- 이유: image_path를 백엔드-중립적인 "키"로 두면 local↔minio 전환 시 메시지/워커 코드가 불변(추상화의 목적). 경로 탈출 방어는 신뢰 경계가 불확실한 입력에 대한 값싼 안전장치.
- 주의(확인 필요): doongle-api가 실제로 image_path에 무엇을 넣는지(파일명만 vs `uploads/파일명` vs 절대경로)에 따라 LocalStorage 해석을 맞춰야 한다. 현재는 "base_path 기준 상대경로"를 가정. api가 이미 base를 포함한 경로를 보내면 이중결합 문제가 생기므로 단계 7 로컬 검증에서 실제 메시지로 확인한다.

## 2026-06-14 — (단계3) jobs 최소 매핑, update는 Core 문, 동기 엔진은 lazy 연결
- 결정: `db.py`에 동기 SQLAlchemy 엔진(`create_engine`, `pool_pre_ping=True`)과 `sessionmaker`. `Job` ORM은 `jobs` 테이블을 최소 컬럼(job_id, status, result)만 매핑하고 job_id를 ORM primary_key로 선언. 갱신은 ORM 식별자 대신 Core `update(Job).where(job_id==...)` 문으로 하고 rowcount를 반환(0이면 "job 없음" 경고). `update_job(session_factory, job_id, status, result)` 헬퍼가 자체 세션·커밋 관리.
- 이유: api가 소유한 테이블이라 실제 PK 구성(별도 id PK 등)을 모른다. Core update 문은 매핑된 PK와 무관하게 job_id 조건으로 동작해 안전. job_id를 ORM PK로 둔 건 매핑 성립을 위한 최소 선언일 뿐(실제 update 경로는 Core라 영향 없음). pool_pre_ping으로 끊긴 커넥션 자동 감지(Kafka 외 DB 재연결성도 확보).
- 비고: `create_engine`은 DBAPI 드라이버(psycopg2)를 즉시 import하지만 DB 연결은 첫 쿼리까지 열지 않는다(시작 시 DB down이어도 기동 가능). 검증은 인메모리 sqlite로 ORM/update_job 동작 확인 + postgresql URL로 기동(연결 안 함) 확인.
- 확인 필요: jobs의 실제 컬럼명/타입(job_id가 uuid인지 text인지, status enum 종류). 단계 7에서 api의 실제 테이블로 확정.

## 2026-06-14 — (단계4) 추론은 ImageClassifier로 캡슐화, 입력은 바이트, 출력은 top-1 (라벨, 확률)
- 결정: `classifier.py`의 `ImageClassifier(model_name)`가 시작 시 transformers `pipeline("image-classification")`을 1회 로드(GPU 있으면 device=0, 없으면 -1). `classify(image_bytes) -> (label, score)`는 바이트를 `PIL.Image`로 디코드(`convert("RGB")`) 후 top-1 반환. 디코드/추론 실패는 예외로 올려 호출자(단계5 루프)가 잡게 한다.
- 이유: 옛 worker는 URL 다운로드였지만 이제 스토리지가 준 바이트를 받는다 → 추론 모듈은 바이트만 알면 되고 스토리지/네트워크와 분리. RGB 변환으로 RGBA·흑백 입력 안전. 모델 1회 로드는 핵심 설계(메시지마다 로드 금지).
- result 저장 형태: DB `result`에는 **라벨 문자열만** 넣는다(TASKS "result=라벨"). 확률(score)은 로그로만 남긴다.
- 검증: Mac CPU에서 ViT 실제 로드+합성 이미지 1장 추론으로 (라벨, 확률) 반환 확인, 깨진 바이트는 UnidentifiedImageError. (torch/transformers는 로컬 .venv에만 설치, 깃 미포함)

## 2026-06-14 — (단계5) 메인 루프: 2중 에러 격리 + 실패 job은 failed로, 재연결은 바깥 루프
- 결정: `run_consumer`가 바깥 while로 KafkaConsumer를 만들고 `for msg in consumer`로 소비. 메시지 처리는 `process_message`(consume payload -> storage.load -> classify -> update_job). 에러 격리는 2중:
  (1) `process_message` 내부 — load/classify 실패는 잡아서 해당 job을 `status=failed`로 표시하고 리턴(다음 메시지 진행),
  (2) for 루프 — 그 외 예외(JSON 파싱, DB update 실패 등)를 잡아 로깅 후 continue.
  바깥 while + try/except는 Kafka 연결 자체가 끊기면 5초 후 재연결.
- 이유: "에러나도 안 죽고 계속 + Kafka 끊기면 재연결" 요구를 충족. 실패 job을 failed로 남기는 건 TASKS의 "status=done"을 넘어선 추가지만, 안 하면 폴링 UI가 pending에서 영원히 멈춘다 → 실패도 종료 상태로 만들어 사용자에게 결과를 보여준다. job_id가 없는 메시지는 update 불가라 skip만.
- 커밋/오프셋: `enable_auto_commit=True`, `auto_offset_reset="earliest"`. 실패해도 failed로 기록 후 오프셋 진행 → 같은 메시지 무한 재처리 안 함(단순성 우선). group_id는 settings(KAFKA_GROUP_ID)에서 — 같은 group이면 Kafka가 워커들에 분배(수평 확장).
- 검증: process_message를 fake storage/classifier + sqlite로 done/failed/skip 3경로 단위 확인. 실제 Kafka 연결·재연결·그룹 분배는 단계 7.

## 2026-06-14 — (단계6) Dockerfile: 설정 ENV 하드코딩 제거, 전체 모듈 복사, --platform 고정 유지
- 결정: 베이스 `pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime`. 옛 Dockerfile의 하드코딩 ENV(KAFKA_BROKER/TOPIC/MODEL)를 **제거** — 설정은 런타임에 k8s ConfigMap/Secret로 주입(코드 컨벤션: 값 하드코딩 금지). 단일 worker.py만 복사하던 것을 config/storage/db/classifier/worker 전체로 확장. `PYTHONUNBUFFERED=1`로 로그 즉시 flush. `.dockerignore`로 .venv/uploads/.env/.git/docs 등 제외.
- `FROM --platform=linux/amd64` 고정 유지: 개발은 Mac(arm64), 배포는 amd64 GPU 노드 → 평범한 `docker build`로도 amd64 이미지가 나오게 강제. `docker build --check`가 이를 린트 경고(FromPlatformFlagConstDisallowed)로 띄우지만, 빌드 호스트에 의존하지 않는 확실성을 위해 의도적으로 둔다(CI에서 --platform 주는 방식의 대안이지만 더 foolproof).
- torch는 requirements에 있어도 베이스에 이미 있어 재설치 안 됨. psycopg2-binary/transformers/kafka-python/Pillow는 wheel이라 apt 빌드 의존성 불필요.
- 검증: `docker build --check` 통과(메타데이터 resolve OK, 위 경고 1건만). 실제 빌드/실행은 도커 없는 로컬 검증(단계7) 범위 밖 — 배포(doongle-k8s)에서.

## 2026-06-14 — MinioStorage 구현 (doongle-api와 동일 계약, 워커는 load만)
- 결정: storage.py의 MinioStorage 스텁을 실제 구현으로 교체. doongle-api(app/core/storage.py)와 동일한 계약을 따른다.
  - image_path는 MinIO **오브젝트 키**(예: "abc123.jpeg"). 버킷명은 키/메시지에 넣지 않고 **env(MINIO_BUCKET)로만** 안다(단일 버킷). 버킷은 미리 생성돼 있다고 가정하고 워커가 만들지 않는다.
  - 클라이언트는 minio 공식 동기 SDK. 워커가 동기 코드라 async 없이 그대로 사용. `__init__`에서 `minio.Minio` 1회 생성. import는 `__init__` 안에서 지연 — local 백엔드만 쓰면 minio 미설치여도 동작.
  - **워커는 load()만 구현/사용한다. save()는 api 책임.** save/load 계약은 공유하되 각 서비스는 자기가 쓰는 쪽만 구현(워커 storage.py에 save 없음). load는 `get_object(bucket, key).read()` 후 finally로 `close()`+`release_conn()`.
  - 키 기반이라 LocalStorage의 경로 탈출 방어(_resolve)는 MinIO에 불필요.
- config.py: Settings에 minio_endpoint/access_key/secret_key/bucket/secure(bool) 추가. MINIO_SECURE는 "true"/"false" 문자열을 `_get_bool`로 bool 변환. redacted()에 minio 필드 추가하되 minio_secret_key는 ***로 가림. env명/기본값은 api와 일치(MINIO_BUCKET 기본 "images", endpoint localhost:9000).
- get_storage()의 minio 분기를 실제 인자 전달(MinioStorage(endpoint=..., ...))로 수정. 의존성에 minio>=7.2.0 추가, .env.example에 MinIO 변수 placeholder 추가.
- 안 건드림: StorageBackend 인터페이스, LocalStorage, worker.py(인터페이스로만 의존 — STORAGE_BACKEND만 바꾸면 워커 코드 불변).
- 검증: load_settings/redacted(secret 마스킹, secure bool), local 분기 유지, minio 분기에서 클라이언트·버킷 생성 확인(서버 없이 생성만). 실제 get_object end-to-end는 MinIO 떠 있는 환경에서.

## 2026-06-14 — 로컬 검증은 도커 없이 python 직접 실행
- 결정: 로컬 테스트 시 워커를 도커로 싸지 않고 Mac에서 python으로 직접 실행한다. localhost Kafka/DB, 같은 ./uploads 경로, CPU 추론.
- 이유: api가 저장한 ./uploads 파일을 같은 파일시스템에서 바로 읽으려면 같은 머신에서 직접 실행이 가장 단순. 도커로 싸면 경로/네트워크 격리로 복잡해짐. GPU 검증은 k3s 배포 단계에서.