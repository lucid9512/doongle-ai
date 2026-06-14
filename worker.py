"""doongle-ai — GPU 추론 워커 진입점.

단계 1: 기본 구조 + 설정 로딩만. (Kafka consumer / 스토리지 / DB / 추론은 이후 단계에서 추가)
"""

import logging

from config import load_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    settings = load_settings()
    logger.info("doongle-ai worker starting")
    logger.info("config loaded: %s", settings.redacted())
    # TODO(단계 2~5): 스토리지 backend, DB 세션, 추론 모델 로드, Kafka consumer 루프


if __name__ == "__main__":
    main()
