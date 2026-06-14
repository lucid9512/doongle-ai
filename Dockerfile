# GPU 추론 워커 이미지. 베이스에 CUDA+torch 포함(k3s GPU 노드는 amd64).
FROM --platform=linux/amd64 pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

# 로그가 버퍼링 없이 바로 stdout에 나오도록(k8s 로그 가시성).
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# 의존성 먼저(레이어 캐시). torch는 베이스 이미지에 이미 있어 재설치되지 않는다.
COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

# 워커 소스(설정값은 하드코딩하지 않고 런타임 환경변수=ConfigMap/Secret로 주입).
COPY config.py storage.py db.py classifier.py worker.py /app/

CMD ["python", "worker.py"]
