FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    APP_DATA_DIR=/var/lib/protocolo-lupita \
    PATH="/app/.venv/bin:${PATH}"

WORKDIR /app

RUN python -m pip install --no-cache-dir uv \
    && groupadd --system --gid 10001 lupita \
    && useradd --system --uid 10001 --gid lupita --no-create-home \
       --home-dir /nonexistent --shell /usr/sbin/nologin lupita \
    && install -d -o lupita -g lupita /var/lib/protocolo-lupita

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY app/ ./app/
COPY data/ ./data/

USER lupita:lupita

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
