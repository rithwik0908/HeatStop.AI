FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=10000 \
    HEATSTOP_BACKEND_PORT=8000 \
    HEATSTOP_API_URL=http://127.0.0.1:8000 \
    HEATSTOP_ENABLE_PRETRAINED_VISION=0 \
    HEATSTOP_ENABLE_COMMUNITY_UPLOADS=0 \
    HEATSTOP_CORS_ALLOW_ORIGINS=http://localhost:8501,http://127.0.0.1:8501 \
    HEATSTOP_CORS_ALLOW_CREDENTIALS=0

WORKDIR /app

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .
RUN chmod +x scripts/start_public.sh scripts/share_dashboard.sh

EXPOSE 10000

CMD ["./scripts/start_public.sh"]
