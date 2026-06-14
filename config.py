"""환경변수 기반 설정 로딩.

설정은 모두 환경변수로 읽는다(.env 로컬, k8s는 ConfigMap/Secret).
코드에 값/비밀값을 하드코딩하지 않는다.
"""

from __future__ import annotations

import os
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 로컬 개발 편의를 위해 .env가 있으면 읽는다. 배포(k8s)에서는 .env 없이 환경변수가 주입된다.
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # python-dotenv가 없으면 조용히 넘어가고, 순수 환경변수만 사용한다.
    pass


def _get(name: str, default: str | None = None, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"required environment variable not set: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    kafka_broker: str
    kafka_topic: str
    kafka_group_id: str
    database_url: str
    model: str
    storage_backend: str
    local_storage_path: str

    def redacted(self) -> dict:
        """로그용. 비밀값(DATABASE_URL)은 가린다."""
        return {
            "kafka_broker": self.kafka_broker,
            "kafka_topic": self.kafka_topic,
            "kafka_group_id": self.kafka_group_id,
            "database_url": _redact_url(self.database_url),
            "model": self.model,
            "storage_backend": self.storage_backend,
            "local_storage_path": self.local_storage_path,
        }


def _redact_url(url: str) -> str:
    """postgresql://user:pass@host:5432/db -> postgresql://user:***@host:5432/db"""
    if not url or "@" not in url or "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    creds, host = rest.split("@", 1)
    if ":" in creds:
        user, _ = creds.split(":", 1)
        creds = f"{user}:***"
    return f"{scheme}://{creds}@{host}"


def load_settings() -> Settings:
    return Settings(
        kafka_broker=_get("KAFKA_BROKER", "localhost:9092"),
        kafka_topic=_get("KAFKA_TOPIC", "image-upload"),
        kafka_group_id=_get("KAFKA_GROUP_ID", "doongle-ai-workers"),
        database_url=_get("DATABASE_URL", required=True),
        model=_get("MODEL", "google/vit-base-patch16-224"),
        storage_backend=_get("STORAGE_BACKEND", "local"),
        local_storage_path=_get("LOCAL_STORAGE_PATH", "./uploads"),
    )
