FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends -y ffmpeg libsndfile1 \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system hutao \
    && adduser --system --ingroup hutao --home /app hutao

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY migrations ./migrations
COPY scripts/apply_database_v2_migrations.py ./scripts/apply_database_v2_migrations.py
COPY scripts/semantic_memory_sync.py ./scripts/semantic_memory_sync.py

RUN mkdir -p /data/storage /data/tmp \
    && chown -R hutao:hutao /app /data

USER hutao

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
