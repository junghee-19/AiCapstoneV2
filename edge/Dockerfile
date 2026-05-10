FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
# torch/torchvision 은 CPU-only 인덱스에서 먼저 설치 — NVIDIA CUDA 라이브러리(약 2GB) 다운로드 회피.
# 이후 -r requirements.txt 는 이미 만족된 버전을 그대로 사용한다.
RUN pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu \
        torch==2.5.1 torchvision==0.20.1
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN cp .env.example .env

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
