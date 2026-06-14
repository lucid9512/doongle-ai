FROM --platform=linux/amd64 pytorch/pytorch:2.4.0-cuda12.1-cudnn9-runtime

ENV KAFKA_BROKER=localhost:9092
ENV KAFKA_TOPIC=image-jobs
ENV MODEL=google/vit-base-patch16-224

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && \
    pip install --no-cache-dir -r /app/requirements.txt

COPY worker.py /app/worker.py

CMD ["python", "worker.py"]
