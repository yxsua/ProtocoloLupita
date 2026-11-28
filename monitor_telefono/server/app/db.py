from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator


def _connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    return connection


@contextmanager
def _connection(path: Path) -> Iterator[sqlite3.Connection]:
    connection = _connect(path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connection(path) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS dispositivos (
                id TEXT PRIMARY KEY,
                nombre TEXT NOT NULL CHECK(length(nombre) BETWEEN 1 AND 80),
                token_hash TEXT NOT NULL UNIQUE,
                creado_en TEXT NOT NULL,
                ultimo_contacto TEXT,
                apps_permitidas TEXT NOT NULL DEFAULT '[]',
                estado TEXT NOT NULL DEFAULT 'activo'
                    CHECK(estado IN ('activo', 'revocado'))
            );

            CREATE TABLE IF NOT EXISTS enrolamientos (
                id TEXT PRIMARY KEY,
                codigo_hash TEXT NOT NULL UNIQUE,
                nombre_sugerido TEXT NOT NULL CHECK(length(nombre_sugerido) BETWEEN 1 AND 80),
                apps_sugeridas TEXT NOT NULL DEFAULT '[]',
                creado_en TEXT NOT NULL,
                expira_en TEXT NOT NULL,
                estado TEXT NOT NULL DEFAULT 'pendiente'
                    CHECK(estado IN ('pendiente', 'canjeado', 'caducado')),
                dispositivo_id TEXT REFERENCES dispositivos(id) ON DELETE SET NULL
            );

            CREATE TABLE IF NOT EXISTS eventos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_evento TEXT NOT NULL UNIQUE,
                dispositivo_id TEXT NOT NULL REFERENCES dispositivos(id) ON DELETE CASCADE,
                tipo TEXT NOT NULL CHECK(tipo IN ('notificacion', 'sms', 'llamada')),
                app TEXT NOT NULL,
                remitente TEXT,
                texto TEXT,
                direccion TEXT CHECK(direccion IS NULL OR direccion IN
                    ('entrante', 'saliente', 'perdida')),
                duracion_s INTEGER CHECK(duracion_s IS NULL OR
                    (duracion_s >= 0 AND duracion_s <= 86400)),
                fecha TEXT NOT NULL,
                recibido_en TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_eventos_fecha ON eventos(fecha DESC);
            CREATE INDEX IF NOT EXISTS idx_eventos_dispositivo
                ON eventos(dispositivo_id, id DESC);
            CREATE INDEX IF NOT EXISTS idx_eventos_app ON eventos(app);
            CREATE INDEX IF NOT EXISTS idx_enrolamientos_expira ON enrolamientos(expira_en);
            """
        )
        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(dispositivos)").fetchall()
        }
        if "apps_permitidas" not in columns:
            connection.execute(
                "ALTER TABLE dispositivos ADD COLUMN apps_permitidas TEXT NOT NULL DEFAULT '[]'"
            )


def cleanup_retention(path: Path, retention_days: int) -> int:
    now = datetime.now(timezone.utc)
    cutoff = (now - timedelta(days=retention_days)).isoformat()
    with _connection(path) as connection:
        cursor = connection.execute("DELETE FROM eventos WHERE fecha < ?", (cutoff,))
        connection.execute(
            """
            UPDATE enrolamientos SET estado = 'caducado'
            WHERE estado = 'pendiente' AND expira_en <= ?
            """,
            (now.isoformat(),),
        )
        connection.execute(
            "DELETE FROM enrolamientos WHERE creado_en < ?",
            (cutoff,),
        )
        return cursor.rowcount


def create_device(
    path: Path,
    name: str,
    allowed_apps: list[str] | None = None,
) -> tuple[dict[str, Any], str]:
    device_id = str(uuid.uuid4())
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    created = datetime.now(timezone.utc).isoformat()
    with _connection(path) as connection:
        connection.execute(
            """
            INSERT INTO dispositivos (
                id, nombre, token_hash, creado_en, apps_permitidas, estado
            ) VALUES (?, ?, ?, ?, ?, 'activo')
            """,
            (device_id, name, token_hash, created, json.dumps(allowed_apps or [])),
        )
    return (
        {
            "id": device_id,
            "nombre": name,
            "creado_en": created,
            "ultimo_contacto": None,
            "apps_permitidas": allowed_apps or [],
            "estado": "activo",
        },
        token,
    )


def get_device_by_token_hash(path: Path, token_hash: str) -> dict[str, Any] | None:
    with _connection(path) as connection:
        row = connection.execute(
            """
            SELECT id, nombre, token_hash, creado_en, ultimo_contacto, estado
            FROM dispositivos WHERE token_hash = ?
            """,
            (token_hash,),
        ).fetchone()
    return dict(row) if row else None


def touch_device(path: Path, device_id: str) -> str:
    now = datetime.now(timezone.utc).isoformat()
    with _connection(path) as connection:
        connection.execute(
            "UPDATE dispositivos SET ultimo_contacto = ? WHERE id = ? AND estado = 'activo'",
            (now, device_id),
        )
    return now


def list_devices(path: Path) -> list[dict[str, Any]]:
    with _connection(path) as connection:
        rows = connection.execute(
            """
            SELECT d.id, d.nombre, d.creado_en, d.ultimo_contacto,
                   d.apps_permitidas, d.estado,
                   COUNT(e.id) AS total_eventos
            FROM dispositivos AS d
            LEFT JOIN eventos AS e ON e.dispositivo_id = d.id
            GROUP BY d.id
            ORDER BY d.creado_en DESC
            """
        ).fetchall()
    now = datetime.now(timezone.utc)
    devices = []
    for row in rows:
        device = dict(row)
        try:
            device["apps_permitidas"] = json.loads(device["apps_permitidas"])
        except (TypeError, json.JSONDecodeError):
            device["apps_permitidas"] = []
        try:
            last_seen = datetime.fromisoformat(device["ultimo_contacto"])
            if last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            device["en_linea"] = (
                device["estado"] == "activo"
                and now - last_seen.astimezone(timezone.utc) <= timedelta(minutes=35)
            )
        except (TypeError, ValueError):
            device["en_linea"] = False
        devices.append(device)
    return devices


def list_apps(path: Path) -> list[str]:
    with _connection(path) as connection:
        rows = connection.execute(
            "SELECT DISTINCT app FROM eventos ORDER BY app COLLATE NOCASE"
        ).fetchall()
    return [row["app"] for row in rows]


def get_device(path: Path, device_id: str) -> dict[str, Any] | None:
    with _connection(path) as connection:
        row = connection.execute(
            """
            SELECT id, nombre, creado_en, ultimo_contacto, estado
            FROM dispositivos WHERE id = ?
            """,
            (device_id,),
        ).fetchone()
    return dict(row) if row else None


def revoke_device(path: Path, device_id: str) -> bool:
    with _connection(path) as connection:
        cursor = connection.execute(
            "UPDATE dispositivos SET estado = 'revocado' WHERE id = ?",
            (device_id,),
        )
        return cursor.rowcount == 1


def create_enrollment(
        path: Path,
        suggested_name: str,
        suggested_apps: list[str],
) -> tuple[dict[str, Any], str]:
        alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
        created = datetime.now(timezone.utc)
        expires = created + timedelta(minutes=15)
        for _ in range(5):
            code = "".join(secrets.choice(alphabet) for _ in range(8))
            code_hash = hashlib.sha256(code.encode("ascii")).hexdigest()
            enrollment = {
                "id": str(uuid.uuid4()),
                "nombre_sugerido": suggested_name,
                "apps_sugeridas": suggested_apps,
                "creado_en": created.isoformat(),
                "expira_en": expires.isoformat(),
                "estado": "pendiente",
            }
            try:
                with _connection(path) as connection:
                    connection.execute(
                        """
                        INSERT INTO enrolamientos (
                            id, codigo_hash, nombre_sugerido, apps_sugeridas,
                            creado_en, expira_en, estado
                        ) VALUES (?, ?, ?, ?, ?, ?, 'pendiente')
                        """,
                        (
                            enrollment["id"],
                            code_hash,
                            suggested_name,
                            json.dumps(suggested_apps),
                            enrollment["creado_en"],
                            enrollment["expira_en"],
                        ),
                    )
                return enrollment, code
            except sqlite3.IntegrityError:
                continue
        raise sqlite3.IntegrityError("No se pudo crear un código de enrolamiento único.")


def get_enrollment(path: Path, code: str) -> dict[str, Any] | None:
        code_hash = hashlib.sha256(code.encode("ascii")).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        with _connection(path) as connection:
            row = connection.execute(
                "SELECT * FROM enrolamientos WHERE codigo_hash = ?",
                (code_hash,),
            ).fetchone()
            if row and row["estado"] == "pendiente" and row["expira_en"] <= now:
                connection.execute(
                    "UPDATE enrolamientos SET estado = 'caducado' WHERE id = ?",
                    (row["id"],),
                )
                return {**dict(row), "estado": "caducado"}
        if not row:
            return None
        enrollment = dict(row)
        enrollment["apps_sugeridas"] = json.loads(enrollment["apps_sugeridas"])
        return enrollment


def redeem_enrollment(
        path: Path,
        code: str,
        device_name: str,
        allowed_apps: list[str],
) -> tuple[str, dict[str, Any] | None, str | None]:
        code_hash = hashlib.sha256(code.encode("ascii")).hexdigest()
        now = datetime.now(timezone.utc)
        token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        device_id = str(uuid.uuid4())
        with _connection(path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM enrolamientos WHERE codigo_hash = ?",
                (code_hash,),
            ).fetchone()
            if not row:
                return "invalido", None, None
            if row["estado"] != "pendiente":
                reason = "caducado" if row["estado"] == "caducado" else "usado"
                return reason, None, None
            if row["expira_en"] <= now.isoformat():
                connection.execute(
                    "UPDATE enrolamientos SET estado = 'caducado' WHERE id = ?",
                    (row["id"],),
                )
                return "caducado", None, None

            created = now.isoformat()
            connection.execute(
                """
                INSERT INTO dispositivos (
                    id, nombre, token_hash, creado_en, apps_permitidas, estado
                ) VALUES (?, ?, ?, ?, ?, 'activo')
                """,
                (device_id, device_name, token_hash, created, json.dumps(allowed_apps)),
            )
            connection.execute(
                """
                UPDATE enrolamientos
                SET estado = 'canjeado', dispositivo_id = ?
                WHERE id = ? AND estado = 'pendiente'
                """,
                (device_id, row["id"]),
            )
        device = {
            "id": device_id,
            "nombre": device_name,
            "creado_en": created,
            "ultimo_contacto": None,
            "apps_permitidas": allowed_apps,
            "estado": "activo",
        }
        return "ok", device, token


def delete_device(path: Path, device_id: str) -> bool:
    with _connection(path) as connection:
        cursor = connection.execute("DELETE FROM dispositivos WHERE id = ?", (device_id,))
        return cursor.rowcount == 1


def delete_all_events(path: Path) -> int:
    with _connection(path) as connection:
        cursor = connection.execute("DELETE FROM eventos")
        return cursor.rowcount


def insert_event(
    path: Path,
    device_id: str,
    event: dict[str, Any],
    event_id: str,
) -> tuple[bool, dict[str, Any] | None]:
    received_at = datetime.now(timezone.utc).isoformat()
    values = (
        event_id,
        device_id,
        event["tipo"],
        event["app"],
        event.get("remitente"),
        event.get("texto"),
        event.get("direccion"),
        event.get("duracion_s"),
        event["fecha"],
        received_at,
    )
    with _connection(path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO eventos (
                id_evento, dispositivo_id, tipo, app, remitente, texto,
                direccion, duracion_s, fecha, recibido_en
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        if cursor.rowcount == 0:
            return False, None
        row = connection.execute(
            """
            SELECT e.id, e.id_evento, e.tipo, e.app, e.remitente, e.texto,
                   e.direccion, e.duracion_s, e.fecha, e.recibido_en,
                   d.id AS dispositivo_id, d.nombre AS dispositivo
            FROM eventos AS e
            JOIN dispositivos AS d ON d.id = e.dispositivo_id
            WHERE e.id = ?
            """,
            (cursor.lastrowid,),
        ).fetchone()
    return True, dict(row) if row else None


def query_events(
    path: Path,
    *,
    device_id: str | None = None,
    app: str | None = None,
    event_type: str | None = None,
    text: str | None = None,
    since: str | None = None,
    until: str | None = None,
    cursor_id: int | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    clauses: list[str] = []
    parameters: list[Any] = []
    if device_id:
        clauses.append("e.dispositivo_id = ?")
        parameters.append(device_id)
    if app:
        clauses.append("e.app = ?")
        parameters.append(app)
    if event_type:
        clauses.append("e.tipo = ?")
        parameters.append(event_type)
    if text:
        clauses.append("(e.texto LIKE ? ESCAPE '!' OR e.remitente LIKE ? ESCAPE '!')")
        escaped_text = text.replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = f"%{escaped_text}%"
        parameters.extend((pattern, pattern))
    if since:
        clauses.append("e.fecha >= ?")
        parameters.append(since)
    if until:
        clauses.append("e.fecha <= ?")
        parameters.append(until)
    if cursor_id is not None:
        clauses.append("e.id < ?")
        parameters.append(cursor_id)

    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    parameters.append(limit + 1)
    with _connection(path) as connection:
        rows = connection.execute(
            f"""
            SELECT e.id AS _cursor_id, e.id_evento, e.tipo, e.app, e.remitente,
                   e.texto, e.direccion, e.duracion_s, e.fecha, e.recibido_en,
                   d.id AS dispositivo_id, d.nombre AS dispositivo
            FROM eventos AS e
            JOIN dispositivos AS d ON d.id = e.dispositivo_id
            {where}
            ORDER BY e.id DESC
            LIMIT ?
            """,
            parameters,
        ).fetchall()

    has_more = len(rows) > limit
    visible_rows = rows[:limit]
    items = []
    for row in visible_rows:
        item = dict(row)
        item.pop("_cursor_id", None)
        items.append(item)
    next_cursor = str(visible_rows[-1]["_cursor_id"]) if has_more and visible_rows else None
    return {"items": items, "next_cursor": next_cursor}

