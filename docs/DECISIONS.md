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

## 2026-06-14 — 로컬 검증은 도커 없이 python 직접 실행
- 결정: 로컬 테스트 시 워커를 도커로 싸지 않고 Mac에서 python으로 직접 실행한다. localhost Kafka/DB, 같은 ./uploads 경로, CPU 추론.
- 이유: api가 저장한 ./uploads 파일을 같은 파일시스템에서 바로 읽으려면 같은 머신에서 직접 실행이 가장 단순. 도커로 싸면 경로/네트워크 격리로 복잡해짐. GPU 검증은 k3s 배포 단계에서.