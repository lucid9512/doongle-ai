"""ViT 이미지 분류 추론 모듈.

모델은 시작 시 1회만 로드(메시지마다 로드 금지)하고, consume 루프에서 재사용한다.
GPU가 있으면 GPU(device=0), 없으면 CPU(-1)를 자동 선택한다.
입력은 이미지 바이트(스토리지가 읽어준 원본), 출력은 top-1 (라벨, 확률).
"""

from __future__ import annotations

import io
import logging

from PIL import Image
import torch
from transformers import pipeline

logger = logging.getLogger(__name__)


class ImageClassifier:
    def __init__(self, model_name: str):
        use_cuda = torch.cuda.is_available()
        self.device = 0 if use_cuda else -1
        logger.info(
            "loading model %s on %s", model_name, "cuda:0" if use_cuda else "cpu"
        )
        # image-classification 파이프라인을 1회 생성(가중치/전처리기 포함).
        self.pipe = pipeline(
            "image-classification", model=model_name, device=self.device
        )
        logger.info("model loaded")

    def classify(self, image_bytes: bytes) -> tuple[str, float]:
        """이미지 바이트 -> top-1 (라벨, 확률). 디코드/추론 실패 시 예외를 올린다."""
        # RGBA·흑백 등도 안전하게 RGB로 변환.
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        results = self.pipe(img, top_k=1)
        if not results:
            raise RuntimeError("classifier returned no results")
        top = results[0]
        return top["label"], float(top["score"])
