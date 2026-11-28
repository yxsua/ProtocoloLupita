from __future__ import annotations

import argparse
import os
import sys
import uuid

import httpx


def build_events() -> list[dict[str, object]]:
    return [
        {
            "id_evento": str(uuid.uuid4()),
            "tipo": "notificacion",
            "app": "com.whatsapp",
            "remitente": "Contacto de prueba",
            "texto": 'Mensaje con "comillas", salto de línea\nsegunda línea y emoji 👋',
        },
        {
            "id_evento": str(uuid.uuid4()),
            "tipo": "sms",
            "app": "com.google.android.apps.messaging",
            "from": "+52 442 000 0000",
            "body": "SMS de prueba; no se envía a ningún teléfono.",
        },
        {
            "id_evento": str(uuid.uuid4()),
            "tipo": "llamada",
            "app": "com.android.phone",
            "number": "+52 442 000 0000",
            "texto": "Llamada de prueba",
            "direccion": "perdida",
            "duracion_s": 0,
        },
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Envía eventos ficticios al monitor local; no contacta teléfonos."
    )
    parser.add_argument(
        "--url",
        default=os.getenv("MONITOR_URL", "http://127.0.0.1:8100"),
        help="URL base del monitor (o variable MONITOR_URL).",
    )
    parser.add_argument(
        "--key",
        default=os.getenv("DEVICE_KEY"),
        help="Clave X-Device-Key (o variable DEVICE_KEY).",
    )
    parser.add_argument(
        "--repeat-first",
        action="store_true",
        help="Reenvía el primer evento con el mismo UUID para probar idempotencia.",
    )
    args = parser.parse_args()
    if not args.key:
        parser.error("Indica --key o configura DEVICE_KEY con la clave creada en Dispositivos.")

    endpoint = f"{args.url.rstrip('/')}/api/eventos"
    events = build_events()
    try:
        with httpx.Client(timeout=10) as client:
            for event in events:
                response = client.post(
                    endpoint,
                    headers={"X-Device-Key": args.key},
                    json=event,
                )
                if response.status_code != 201:
                    print(
                        f"El servidor rechazó un evento: HTTP {response.status_code}.",
                        file=sys.stderr,
                    )
                    return 1
                print(f"Evento enviado: {event['tipo']} desde {event['app']}")

            if args.repeat_first:
                response = client.post(
                    endpoint,
                    headers={"X-Device-Key": args.key},
                    json=events[0],
                )
                if response.status_code != 200:
                    print(
                        f"La prueba de duplicado falló: HTTP {response.status_code}.",
                        file=sys.stderr,
                    )
                    return 1
                print("Duplicado reconocido; no se guardó una segunda copia.")
    except httpx.RequestError as exc:
        print(f"No se pudo conectar al monitor: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
