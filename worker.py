"""doongle-ai — GPU 추론 워커 진입점.

단계 1~2: 설정 로딩 + 스토리지 백엔드 선택. (Kafka consumer / DB / 추론은 이후 단계에서 추가)
"""

import logging

from config import load_settings
from storage import get_storage

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
    # TODO(단계 3~5): DB 세션, 추론 모델 로드, Kafka consumer 루프


if __name__ == "__main__":
    main()
