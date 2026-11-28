#!/usr/bin/env sh
set -eu

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
SERVER="$ROOT/server"
ENV_FILE="$ROOT/.env"

if [ ! -f "$ENV_FILE" ]; then
  cp "$ROOT/.env.example" "$ENV_FILE"
  printf '%s\n' "Se creó monitor_telefono/.env. Configura MONITOR_PASSWORD y SECRET_KEY y vuelve a ejecutar." >&2
  exit 1
fi

set -a
. "$ENV_FILE"
set +a

: "${MONITOR_PASSWORD:?Configura MONITOR_PASSWORD en monitor_telefono/.env}"
: "${SECRET_KEY:?Configura SECRET_KEY en monitor_telefono/.env}"
if [ "${#SECRET_KEY}" -lt 32 ]; then
  printf '%s\n' "SECRET_KEY debe contener al menos 32 caracteres aleatorios." >&2
  exit 1
fi
PUERTO="${PUERTO:-8100}"

if [ ! -x "$SERVER/.venv/bin/python" ]; then
  python3 -m venv "$SERVER/.venv"
fi
"$SERVER/.venv/bin/python" -m pip install -r "$SERVER/requirements.txt"
cd "$SERVER"
PYTHONPATH="$SERVER" exec "$SERVER/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port "$PUERTO" --proxy-headers --forwarded-allow-ips=127.0.0.1
