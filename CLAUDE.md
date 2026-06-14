# CLAUDE.md

이 파일은 doongle-ai 레포에서 작업하는 에이전트(Claude Code)가 항상 따르는 상시 컨텍스트다.

## 작업 절차 (매 작업 시작 시)
1. `docs/TASKS.md`를 읽어 현재 진행할 단계를 확인한다.
2. **그 단계만** 수행한다. 다음 단계로 임의로 넘어가지 않는다.
3. 단계가 끝나면 변경 파일을 요약하고 **멈춰서 사용자 확인을 받는다.**
4. 설계상 의미 있는 결정을 내렸거나 기존 결정을 바꿨다면 `docs/DECISIONS.md`에 시간순으로 추가한다.
5. 단계 완료 시 `docs/TASKS.md`의 체크박스를 갱신하고, 코드와 함께 커밋한다.

## 프로젝트 정체성
- doongle-ai는 **GPU 추론 워커**다.
- 역할: Kafka `image-upload` 토픽에서 `{job_id, image_path}` 메시지를 consume → image_path로 이미지를 읽어 → ViT 이미지 분류 추론 → PostgreSQL `jobs` 테이블의 해당 job을 status=done, result=라벨로 update.
- 업로드 게이트웨이(이미지 받기, job 생성, produce)는 doongle-api의 몫이다. **이 레포 범위가 아니다.**
- k8s 매니페스트(Deployment/ConfigMap/Secret)는 doongle-k8s 레포에서 관리한다. 이 레포 범위가 아니다.

## 핵심 설계 결정 (상세 이유는 docs/DECISIONS.md)
- **동기 워커**: kafka-python consumer 루프 + 동기 SQLAlchemy. 추론이 연산 중심(순차)이라 async 이점이 없어 단순한 동기로 간다.
- **수평 확장**: 처리량은 워커 코드를 복잡하게 하지 않고 replica를 늘려 해결. 모든 워커가 같은 `group_id`(예: "doongle-ai-workers")로 컨슈머 그룹을 이뤄 Kafka가 메시지를 분배한다.
- **스토리지 추상화**: `StorageBackend`(load) 인터페이스 + `LocalStorage` 구현. `MinioStorage`는 인터페이스만 두고 추후 구현. `STORAGE_BACKEND` 환경변수로 분기. (doongle-api와 동일한 전략)
- **모델 1회 로드**: ViT(`google/vit-base-patch16-224`)를 시작 시 한 번만 로드. 메시지마다 로드 금지.
- **GPU 분기**: `torch.cuda.is_available()`로 GPU(device=0)/CPU(-1) 자동 선택. 로컬(Mac)은 CPU, k3s(윈1)는 GPU.
- **DB job 모델**: doongle-api의 `jobs` 테이블을 워커에서 최소 컬럼으로 다시 매핑(job_id, status, result). status/result update만 한다.

## 코드 컨벤션
- 설정은 환경변수로 읽는다(.env 로컬, k8s는 ConfigMap/Secret). 코드에 값 하드코딩 금지.
- 로깅: `logging.getLogger(...)` 패턴. print 대신 logger 사용.
- 메시지 처리 중 에러가 나도 워커는 죽지 않고 다음 메시지를 계속 처리한다.
- Kafka 연결이 끊기면 재연결을 시도한다.
- 비밀값(DB URL, MinIO 키)은 코드/깃에 하드코딩하지 않고 환경변수로만.

## 작업 원칙
- 한 단계씩. 한 번에 전체를 구현하지 않는다.
- 커밋은 단계별 의미 단위, 커밋 메시지는 영어 + (step N) 표기.