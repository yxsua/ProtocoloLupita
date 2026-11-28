FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DATABASE_PATH=/data/monitor.sqlite3 \
    PUERTO=8100

WORKDIR /srv/monitor

COPY server/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && addgroup --system --gid 10001 monitor \
    && adduser --system --uid 10001 --ingroup monitor --home /nonexistent monitor \
    && mkdir -p /data \
    && chown monitor:monitor /data

COPY server/app ./app
COPY scripts/backup_sqlite.py /usr/local/bin/backup_sqlite.py

USER monitor
EXPOSE 8100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100", "--proxy-headers", "--forwarded-allow-ips=*"]
