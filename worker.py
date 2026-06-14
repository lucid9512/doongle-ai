"""doongle-ai — GPU 추론 워커.

Kafka `image-upload` 토픽에서 {job_id, image_path}를 consume → storage로 이미지 바이트를
읽어 → ViT 추론 → PostgreSQL jobs 테이블을 status=done, result=라벨로 update.

- 메시지 처리 중 에러가 나도 워커는 죽지 않고 다음 메시지를 계속 처리한다.
- Kafka 연결이 끊기면 재연결을 시도한다.
- 모든 워커가 같은 group_id로 컨슈머 그룹을 이뤄 Kafka가 메시지를 분배한다(수평 확장).
"""

import json
import time
import logging
import traceback

from kafka import KafkaConsumer

from config import load_settings, Settings
from storage import get_storage, StorageBackend
from db import create_db_engine, create_session_factory, update_job
from classifier import ImageClassifier

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

RECONNECT_DELAY_SEC = 5


def process_message(
    raw: str,
    storage: StorageBackend,
    classifier: ImageClassifier,
    session_factory,
) -> None:
    """메시지 1건 처리: consume payload -> load -> classify -> DB update.

    잘못된 메시지(필드 누락)는 건너뛰고, 추론 실패는 해당 job을 failed로 표시한다.
    어느 경우에도 예외를 밖으로 던지지 않아(루프가 다음 메시지로 진행), 워커는 죽지 않는다.
    단, DB update 자체의 실패는 호출자(루프)가 잡도록 그대로 올라갈 수 있다.
    """
    data = json.loads(raw)
    job_id = data.get("job_id")
    image_path = data.get("image_path")
    if not job_id or not image_path:
        logger.warning("message missing job_id/image_path; skipping: %s", raw)
        return

    logger.info("processing job_id=%s image_path=%s", job_id, image_path)
    try:
        image_bytes = storage.load(image_path)
        label, score = classifier.classify(image_bytes)
    except Exception:
        logger.error("inference failed job_id=%s:\n%s", job_id, traceback.format_exc())
        update_job(session_factory, job_id, "failed", None)
        return

    update_job(session_factory, job_id, "done", label)
    logger.info("job done job_id=%s -> %s (%.4f)", job_id, label, score)


def run_consumer(
    settings: Settings,
    storage: StorageBackend,
    classifier: ImageClassifier,
    session_factory,
) -> None:
    """Kafka consumer 루프. 연결이 끊기면 재연결한다."""
    while True:
        try:
            consumer = KafkaConsumer(
                settings.kafka_topic,
                bootstrap_servers=[settings.kafka_broker],
                group_id=settings.kafka_group_id,
                value_deserializer=lambda m: m.decode("utf-8"),
                auto_offset_reset="earliest",
                enable_auto_commit=True,
            )
            logger.info(
                "connected to kafka; broker=%s topic=%s group=%s",
                settings.kafka_broker,
                settings.kafka_topic,
                settings.kafka_group_id,
            )
            for msg in consumer:
                try:
                    process_message(msg.value, storage, classifier, session_factory)
                except Exception:
                    # 한 메시지의 실패가 워커를 죽이지 않는다 — 로깅 후 다음 메시지로.
                    logger.error(
                        "failed to process message:\n%s", traceback.format_exc()
                    )
                    continue
        except Exception:
            logger.error(
                "kafka consumer error, reconnecting in %ds:\n%s",
                RECONNECT_DELAY_SEC,
                traceback.format_exc(),
            )
            time.sleep(RECONNECT_DELAY_SEC)


def main() -> None:
    settings = load_settings()
    logger.info("doongle-ai worker starting")
    logger.info("config loaded: %s", settings.redacted())

    storage = get_storage(settings)
    logger.info("storage ready: %s", type(storage).__name__)

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    logger.info("db engine ready")

    classifier = ImageClassifier(settings.model)

    run_consumer(settings, storage, classifier, session_factory)


if __name__ == "__main__":
    main()
