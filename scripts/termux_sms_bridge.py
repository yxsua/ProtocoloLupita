"""Puente SMS para Android (Termux + Termux:API).

Lee los SMS recibidos con `termux-sms-list` y los envia al servidor local
(POST /sms/api/device-webhook). Corre todo dentro del telefono: no requiere WiFi.

Garantias de seguridad:
- Nunca responde SMS ni abre enlaces (solo lee la bandeja y hace POST a localhost).
- El servidor sanea PII y desactiva URLs (hxxp://) antes de guardar.

Uso en Termux:
    python scripts/termux_sms_bridge.py
    python scripts/termux_sms_bridge.py --url http://127.0.0.1:8000/sms/api/device-webhook --municipio Guadalajara
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import time
import urllib.error
import urllib.request

DEFAULT_URL = "http://127.0.0.1:8000/sms/api/device-webhook"


def leer_sms(limite: int) -> list[dict]:
    """Lee los ultimos SMS de la bandeja de entrada usando Termux:API."""
    salida = subprocess.run(
        ["termux-sms-list", "-l", str(limite), "-t", "inbox"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if salida.returncode != 0:
        raise RuntimeError(salida.stderr.strip() or "termux-sms-list fallo")
    datos = json.loads(salida.stdout or "[]")
    return datos if isinstance(datos, list) else []


def id_sms(sms: dict) -> str:
    if sms.get("_id") is not None:
        return str(sms["_id"])
    base = f"{sms.get('number', '')}|{sms.get('received', '')}|{sms.get('body', '')}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def enviar(url: str, sms: dict, municipio: str) -> None:
    payload = {
        "sender": str(sms.get("number", "")),
        "body": str(sms.get("body", "")),
        "municipality": municipio,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        resp.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Puente SMS Termux -> Protocolo Lupita")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--municipio", default="Guadalajara")
    parser.add_argument("--intervalo", type=float, default=5.0, help="segundos entre lecturas")
    parser.add_argument("--limite", type=int, default=20)
    parser.add_argument(
        "--incluir-existentes",
        action="store_true",
        help="enviar tambien los SMS que ya estaban en la bandeja al iniciar",
    )
    args = parser.parse_args()

    vistos: set[str] = set()
    if not args.incluir_existentes:
        vistos = {id_sms(s) for s in leer_sms(args.limite)}
        print(f"Ignorando {len(vistos)} SMS existentes. Esperando nuevos...")

    while True:
        try:
            for sms in reversed(leer_sms(args.limite)):
                clave = id_sms(sms)
                if clave in vistos:
                    continue
                try:
                    enviar(args.url, sms, args.municipio)
                    vistos.add(clave)
                    print(f"Enviado SMS de {sms.get('number', '?')}")
                except (urllib.error.URLError, OSError) as exc:
                    print(f"No se pudo enviar (¿servidor encendido?): {exc}")
                    break
        except Exception as exc:  # noqa: BLE001 - mantener el puente vivo
            print(f"Error leyendo SMS: {exc}")
        time.sleep(args.intervalo)


if __name__ == "__main__":
    main()
