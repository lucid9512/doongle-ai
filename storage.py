"""스토리지 추상화.

워커는 메시지의 image_path로 StorageBackend.load()를 통해 이미지 바이트를 읽는다.
doongle-api와 동일한 계약: 로컬은 LocalStorage(같은 ./uploads 파일 읽기),
배포는 MinioStorage(네트워크). STORAGE_BACKEND 환경변수로 전환하고 워커 코드는 불변.
"""

from __future__ import annotations

import os
import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """image_path -> 이미지 바이트."""

    @abstractmethod
    def load(self, image_path: str) -> bytes:
        """image_path가 가리키는 이미지의 원본 바이트를 반환한다."""
        raise NotImplementedError


class LocalStorage(StorageBackend):
    """로컬 파일시스템에서 읽는다. image_path는 base_path 기준 상대경로(또는 절대경로)."""

    def __init__(self, base_path: str):
        self.base_path = base_path

    def load(self, image_path: str) -> bytes:
        full_path = self._resolve(image_path)
        with open(full_path, "rb") as f:
            return f.read()

    def _resolve(self, image_path: str) -> str:
        # api가 절대경로를 넘기면 그대로, 상대경로면 base_path 기준으로 합친다.
        if os.path.isabs(image_path):
            return image_path
        base = os.path.abspath(self.base_path)
        full = os.path.abspath(os.path.join(base, image_path))
        # 경로 탈출(../../etc/passwd) 방어.
        if full != base and not full.startswith(base + os.sep):
            raise ValueError(f"image_path escapes storage base: {image_path!r}")
        return full


class MinioStorage(StorageBackend):
    """MinIO(S3 호환) 백엔드. 인터페이스만 두고 배포 단계에서 구현한다."""

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "MinioStorage는 아직 구현되지 않았다 (배포 단계에서 구현 예정)"
        )

    def load(self, image_path: str) -> bytes:
        raise NotImplementedError


def get_storage(settings) -> StorageBackend:
    """STORAGE_BACKEND 환경변수에 따라 백엔드를 고른다."""
    backend = (settings.storage_backend or "").lower()
    if backend == "local":
        logger.info("storage backend: local (base_path=%s)", settings.local_storage_path)
        return LocalStorage(settings.local_storage_path)
    if backend == "minio":
        return MinioStorage()
    raise ValueError(f"unknown STORAGE_BACKEND: {settings.storage_backend!r}")
