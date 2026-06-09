FROM python:3.12-slim

WORKDIR /app

# HEIC (pillow-heif) + RAW (rawpy) 在部分架构下需要源码编译
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       build-essential pkg-config libraw-dev libheif-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /images /data

EXPOSE 8080

ENV FLASK_ENV=production
ENV IMAGES_DIR=/images
ENV DATA_DIR=/data
ENV SECRET_KEY=inkjoy-manager-please-change-me
ENV TZ=Asia/Shanghai

CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "120", "app:app"]
