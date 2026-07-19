FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30"

COPY server/src server/src
COPY web web
COPY src/hexmapper/assets assets
COPY map.hexmap2 .

ENV HEXMAP_WEB_DIR=/app/web \
    HEXMAP_ASSETS_DIR=/app/assets \
    HEXMAP_DB=/data/map.db \
    HEXMAP_SEED=/app/map.hexmap2

RUN mkdir -p /data

EXPOSE 8080

CMD ["uvicorn", "--app-dir", "server/src", "hexserver.app:app", "--host", "0.0.0.0", "--port", "8080"]
