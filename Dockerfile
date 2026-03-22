FROM python:3.12-slim

WORKDIR /app

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
