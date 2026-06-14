"""doongle-ai — GPU 추론 워커 진입점.

단계 1~3: 설정 로딩 + 스토리지 백엔드 선택 + DB 엔진/세션. (Kafka consumer / 추론은 이후 단계)
"""

import logging

from config import load_settings
from storage import get_storage
from db import create_db_engine, create_session_factory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    logger.info("doongle-ai worker starting")
    logger.info("config loaded: %s", settings.redacted())

    storage = get_storage(settings)
    logger.info("storage ready: %s", type(storage).__name__)

    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    logger.info("db engine ready")
    # TODO(단계 4~5): 추론 모델 로드, Kafka consumer 루프


if __name__ == "__main__":
    main()
