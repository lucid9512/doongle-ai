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
    """MinIO(S3 호환) 오브젝트 스토리지. (doongle-api와 동일 계약)

    - image_path는 오브젝트 키(예: "abc123.jpeg"). 버킷명은 키/메시지에 싣지 않고
      env(MINIO_BUCKET)로만 안다(단일 버킷).
    - 버킷은 콘솔에서 미리 만든다고 가정하고 여기서 생성하지 않는다(존재 가정).
    - 워커는 동기 코드라 minio 동기 SDK를 그대로 쓴다. 워커는 load()만 구현/사용한다
      (save는 api 책임 — 계약은 공유하되 각자 자기가 쓰는 쪽만 구현).
    - 키 기반이라 LocalStorage의 경로 탈출 방어(_resolve)는 해당 없음.
    """

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        secure: bool,
    ):
        # minio 클라이언트는 __init__에서 1회 생성해 재사용한다.
        # local 백엔드만 쓰는 경우 minio 미설치여도 되도록 import는 여기서(지연).
        from minio import Minio

        self._bucket = bucket
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        logger.info(
            "storage backend: minio (endpoint=%s, bucket=%s, secure=%s)",
            endpoint,
            bucket,
            secure,
        )

    def load(self, image_path: str) -> bytes:
        response = self._client.get_object(self._bucket, image_path)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()


def get_storage(settings) -> StorageBackend:
    """STORAGE_BACKEND 환경변수에 따라 백엔드를 고른다."""
    backend = (settings.storage_backend or "").lower()
    if backend == "local":
        logger.info("storage backend: local (base_path=%s)", settings.local_storage_path)
        return LocalStorage(settings.local_storage_path)
    if backend == "minio":
        return MinioStorage(
            endpoint=settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            bucket=settings.minio_bucket,
            secure=settings.minio_secure,
        )
    raise ValueError(f"unknown STORAGE_BACKEND: {settings.storage_backend!r}")
