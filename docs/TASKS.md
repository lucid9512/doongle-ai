# TASKS

doongle-ai(GPU 추론 워커) 구현 단계. 에이전트는 현재 단계만 수행하고 멈춰서 확인받는다.
완료 시 체크박스를 갱신하고 코드와 함께 커밋한다.

> 기존 레포에 옛 worker.py(image_url 기반, print만)가 있으면 현재 설계({job_id, image_path} + DB update)에 안 맞으므로 새로 작성/교체한다.

## 진행 예정
- [x] 단계 1 — 기본 구조 + 설정
  - 의존성: kafka-python, sqlalchemy, psycopg2(또는 psycopg), pillow, torch, transformers
  - 환경변수 설정 읽기: KAFKA_BROKER, KAFKA_TOPIC=image-upload, KAFKA_GROUP_ID=doongle-ai-workers, DATABASE_URL, MODEL=google/vit-base-patch16-224, STORAGE_BACKEND=local, LOCAL_STORAGE_PATH=./uploads
  - .env.example 작성

- [x] 단계 2 — 스토리지 추상화
  - StorageBackend(ABC): load(image_path) -> bytes
  - LocalStorage 구현(파일 읽기), MinioStorage는 자리만(미구현)
  - STORAGE_BACKEND 환경변수로 분기

- [x] 단계 3 — DB 연결 + Job 모델
  - 동기 SQLAlchemy 엔진/세션
  - jobs 테이블 최소 매핑(job_id, status, result) — api와 같은 테이블
  - update 헬퍼: job_id로 찾아 status=done, result 기록

- [ ] 단계 4 — 추론 모듈
  - ViT 파이프라인 모델 1회 로드(시작 시), GPU 분기(torch.cuda.is_available)
  - 이미지 바이트 -> 분류 -> top-1 라벨+확률

- [ ] 단계 5 — 메인 워커 루프
  - kafka-python consumer(group_id로 컨슈머 그룹)
  - 메시지 {job_id, image_path} consume -> storage.load -> 추론 -> DB update(done)
  - 에러나도 안 죽고 계속, Kafka 끊기면 재연결

- [ ] 단계 6 — Dockerfile
  - 베이스 pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime (x86/amd64)
  - 의존성 설치 + worker 실행

- [ ] 단계 7 — 로컬 검증
  - .env 로컬(localhost Kafka/DB, STORAGE_BACKEND=local, 같은 ./uploads)
  - python으로 직접 실행(도커 아님), api로 이미지 업로드 -> 워커가 consume -> DB job이 pending->done 되는지 확인
  - 화면 카드가 done으로 바뀌는지 확인(CPU 추론이라 느릴 수 있음)