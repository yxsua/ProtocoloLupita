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

from app.crypto import decrypt_text, encrypt_text

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


def initialize(path: Path, encryption_key: str) -> None:
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
                consentimiento_version TEXT NOT NULL DEFAULT 'v1',
                consentimiento_aceptado_en TEXT,
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
                texto_cifrado TEXT,
                riesgo INTEGER NOT NULL DEFAULT 0 CHECK(riesgo BETWEEN 0 AND 100),
                nivel_riesgo TEXT NOT NULL DEFAULT 'bajo'
                    CHECK(nivel_riesgo IN ('bajo', 'medio', 'alto')),
                razones_riesgo TEXT NOT NULL DEFAULT '[]',
                revision_estado TEXT CHECK(revision_estado IS NULL OR revision_estado IN
                    ('confirmado', 'falso_positivo', 'necesita_contacto')),
                revisor_id INTEGER REFERENCES cuentas(id) ON DELETE SET NULL,
                revisado_en TEXT,
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
            CREATE TABLE IF NOT EXISTS cuentas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                rol TEXT NOT NULL CHECK(rol IN ('admin', 'revisor')),
                totp_secret_encrypted TEXT,
                activa INTEGER NOT NULL DEFAULT 1 CHECK(activa IN (0, 1)),
                creada_en TEXT NOT NULL,
                ultimo_acceso TEXT
            );

            CREATE TABLE IF NOT EXISTS evento_reglas (
                evento_id INTEGER NOT NULL REFERENCES eventos(id) ON DELETE CASCADE,
                regla_id TEXT NOT NULL,
                etiqueta TEXT NOT NULL,
                PRIMARY KEY(evento_id, regla_id)
            );

            CREATE TABLE IF NOT EXISTS auditoria (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor_id INTEGER REFERENCES cuentas(id) ON DELETE SET NULL,
                actor TEXT NOT NULL,
                accion TEXT NOT NULL,
                tipo_entidad TEXT NOT NULL,
                entidades_json TEXT NOT NULL,
                creado_en TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_auditoria_fecha ON auditoria(id DESC);
            CREATE TRIGGER IF NOT EXISTS auditoria_solo_insert
                BEFORE UPDATE ON auditoria
                BEGIN SELECT RAISE(ABORT, 'La bitácora es de solo anexado.'); END;
            CREATE TRIGGER IF NOT EXISTS auditoria_sin_borrado
                BEFORE DELETE ON auditoria
                BEGIN SELECT RAISE(ABORT, 'La bitácora es de solo anexado.'); END;
            """
        )
        migrations = {
            "dispositivos": {
                "apps_permitidas": "TEXT NOT NULL DEFAULT '[]'",
                "consentimiento_version": "TEXT NOT NULL DEFAULT 'v1'",
                "consentimiento_aceptado_en": "TEXT",
            },
            "eventos": {
                "texto_cifrado": "TEXT",
                "riesgo": "INTEGER NOT NULL DEFAULT 0",
                "nivel_riesgo": "TEXT NOT NULL DEFAULT 'bajo'",
                "razones_riesgo": "TEXT NOT NULL DEFAULT '[]'",
                "revision_estado": "TEXT",
                "revisor_id": "INTEGER REFERENCES cuentas(id) ON DELETE SET NULL",
                "revisado_en": "TEXT",
            },
        }
        for table, additions in migrations.items():
            columns = {
                row["name"]
                for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for name, declaration in additions.items():
                if name not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {declaration}")

        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_eventos_riesgo ON eventos(nivel_riesgo, id DESC)"
        )
        legacy_rows = connection.execute(
            "SELECT id, texto FROM eventos WHERE texto IS NOT NULL AND texto_cifrado IS NULL"
        ).fetchall()
        for row in legacy_rows:
            ciphertext = encrypt_text(row["texto"], encryption_key)
            connection.execute(
                "UPDATE eventos SET texto = NULL, texto_cifrado = ? WHERE id = ?",
                (ciphertext, row["id"]),
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


def cleanup_privacy_retention(
    path: Path,
    retention_days: int,
    normal_text_hours: int,
    alert_days: int,
) -> int:
    now = datetime.now(timezone.utc)
    normal_text_cutoff = (now - timedelta(hours=normal_text_hours)).isoformat()
    normal_event_cutoff = (now - timedelta(days=retention_days)).isoformat()
    alert_cutoff = (now - timedelta(days=alert_days)).isoformat()
    with _connection(path) as connection:
        connection.execute(
            """
            UPDATE eventos SET texto_cifrado = NULL
            WHERE nivel_riesgo = 'bajo' AND recibido_en < ?
            """,
            (normal_text_cutoff,),
        )
        normal_deleted = connection.execute(
            "DELETE FROM eventos WHERE nivel_riesgo = 'bajo' AND recibido_en < ?",
            (normal_event_cutoff,),
        ).rowcount
        alert_deleted = connection.execute(
            "DELETE FROM eventos WHERE nivel_riesgo IN ('medio', 'alto') AND recibido_en < ?",
            (alert_cutoff,),
        ).rowcount
        connection.execute(
            """
            UPDATE enrolamientos SET estado = 'caducado'
            WHERE estado = 'pendiente' AND expira_en <= ?
            """,
            (now.isoformat(),),
        )
        connection.execute(
            "DELETE FROM enrolamientos WHERE creado_en < ?",
            (normal_event_cutoff,),
        )
        return normal_deleted + alert_deleted


def has_admin(path: Path) -> bool:
    with _connection(path) as connection:
        return connection.execute(
            "SELECT 1 FROM cuentas WHERE rol = 'admin' AND activa = 1 LIMIT 1"
        ).fetchone() is not None


def create_account(
    path: Path,
    username: str,
    password_hash: str,
    role: str,
    totp_secret_encrypted: str | None = None,
) -> int:
    if role not in {"admin", "revisor"}:
        raise ValueError("Rol de cuenta inválido.")
    created = datetime.now(timezone.utc).isoformat()
    with _connection(path) as connection:
        cursor = connection.execute(
            """
            INSERT INTO cuentas (usuario, password_hash, rol, totp_secret_encrypted, creada_en)
            VALUES (?, ?, ?, ?, ?)
            """,
            (username.strip(), password_hash, role, totp_secret_encrypted, created),
        )
        return int(cursor.lastrowid)


def get_account_by_username(path: Path, username: str) -> dict[str, Any] | None:
    with _connection(path) as connection:
        row = connection.execute(
            """
            SELECT id, usuario, password_hash, rol, totp_secret_encrypted, activa
            FROM cuentas WHERE usuario = ? COLLATE NOCASE
            """,
            (username.strip(),),
        ).fetchone()
    return dict(row) if row else None


def get_account(path: Path, account_id: int) -> dict[str, Any] | None:
    with _connection(path) as connection:
        row = connection.execute(
            """
            SELECT id, usuario, rol, activa, creada_en, ultimo_acceso
            FROM cuentas WHERE id = ?
            """,
            (account_id,),
        ).fetchone()
    return dict(row) if row else None


def list_accounts(path: Path) -> list[dict[str, Any]]:
    with _connection(path) as connection:
        rows = connection.execute(
            """
            SELECT id, usuario, rol, activa, creada_en, ultimo_acceso
            FROM cuentas ORDER BY rol, usuario COLLATE NOCASE
            """
        ).fetchall()
    return [dict(row) for row in rows]


def set_account_active(path: Path, account_id: int, active: bool) -> bool:
    with _connection(path) as connection:
        cursor = connection.execute(
            "UPDATE cuentas SET activa = ? WHERE id = ?",
            (int(active), account_id),
        )
        return cursor.rowcount == 1


def record_account_login(path: Path, account_id: int) -> None:
    with _connection(path) as connection:
        connection.execute(
            "UPDATE cuentas SET ultimo_acceso = ? WHERE id = ?",
            (datetime.now(timezone.utc).isoformat(), account_id),
        )


def append_audit(
    path: Path,
    *,
    actor_id: int | None,
    actor: str,
    action: str,
    entity_type: str,
    entity_ids: list[str] | dict[str, Any] | str,
) -> None:
    created = datetime.now(timezone.utc).isoformat()
    entities_json = json.dumps(entity_ids, ensure_ascii=False, separators=(",", ":"))
    with _connection(path) as connection:
        connection.execute(
            """
            INSERT INTO auditoria (actor_id, actor, accion, tipo_entidad, entidades_json, creado_en)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (actor_id, actor[:128], action[:64], entity_type[:64], entities_json, created),
        )


def list_audit(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    with _connection(path) as connection:
        rows = connection.execute(
            """
            SELECT id, actor_id, actor, accion, tipo_entidad, entidades_json, creado_en
            FROM auditoria ORDER BY id DESC LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["entidades"] = json.loads(item.pop("entidades_json"))
        result.append(item)
    return result


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
            SELECT id, nombre, token_hash, creado_en, ultimo_contacto,
                   consentimiento_version, estado
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
        consent_version: str = "v1",
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
                    id, nombre, token_hash, creado_en, apps_permitidas,
                    consentimiento_version, consentimiento_aceptado_en, estado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'activo')
                """,
                (
                    device_id,
                    device_name,
                    token_hash,
                    created,
                    json.dumps(allowed_apps),
                    consent_version,
                    created,
                ),
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
    verdict: dict[str, Any],
    encryption_key: str,
) -> tuple[bool, dict[str, Any] | None]:
    received_at = datetime.now(timezone.utc).isoformat()
    ciphertext = encrypt_text(event.get("texto"), encryption_key)
    values = (
        event_id,
        device_id,
        event["tipo"],
        event["app"],
        event.get("remitente"),
        ciphertext,
        int(verdict.get("riesgo", 0)),
        verdict.get("nivel", "bajo"),
        json.dumps(verdict.get("razones", []), ensure_ascii=False),
        event.get("direccion"),
        event.get("duracion_s"),
        event["fecha"],
        received_at,
    )
    with _connection(path) as connection:
        cursor = connection.execute(
            """
            INSERT OR IGNORE INTO eventos (
                id_evento, dispositivo_id, tipo, app, remitente, texto, texto_cifrado,
                riesgo, nivel_riesgo, razones_riesgo,
                direccion, duracion_s, fecha, recibido_en
            ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            values,
        )
        if cursor.rowcount == 0:
            row = connection.execute(
                """
                SELECT e.id, e.id_evento, e.tipo, e.app, e.remitente,
                       e.texto, e.texto_cifrado, e.riesgo, e.nivel_riesgo,
                       e.razones_riesgo, e.revision_estado, e.revisado_en,
                       e.direccion, e.duracion_s, e.fecha, e.recibido_en,
                       d.id AS dispositivo_id, d.nombre AS dispositivo
                FROM eventos AS e JOIN dispositivos AS d ON d.id = e.dispositivo_id
                WHERE e.id_evento = ?
                """,
                (event_id,),
            ).fetchone()
            return False, _deserialize_event(row, encryption_key) if row else None
        event_row_id = int(cursor.lastrowid)
        for rule in verdict.get("reglas", []):
            connection.execute(
                """
                INSERT OR IGNORE INTO evento_reglas (evento_id, regla_id, etiqueta)
                VALUES (?, ?, ?)
                """,
                (event_row_id, str(rule["id"])[:80], str(rule["etiqueta"])[:200]),
            )
        row = connection.execute(
            """
            SELECT e.id, e.id_evento, e.tipo, e.app, e.remitente,
                   e.texto, e.texto_cifrado, e.riesgo, e.nivel_riesgo,
                   e.razones_riesgo, e.revision_estado, e.revisado_en,
                   e.direccion, e.duracion_s, e.fecha, e.recibido_en,
                   d.id AS dispositivo_id, d.nombre AS dispositivo
            FROM eventos AS e
            JOIN dispositivos AS d ON d.id = e.dispositivo_id
            WHERE e.id = ?
            """,
            (event_row_id,),
        ).fetchone()
    return True, _deserialize_event(row, encryption_key) if row else None


def _deserialize_event(row: sqlite3.Row, encryption_key: str) -> dict[str, Any]:
    item = dict(row)
    ciphertext = item.pop("texto_cifrado", None)
    item["texto"] = decrypt_text(ciphertext, encryption_key)
    item["riesgo"] = int(item.get("riesgo", 0))
    item["razones_riesgo"] = json.loads(item.get("razones_riesgo") or "[]")
    return item


def query_events(
    path: Path,
    encryption_key: str,
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
    if since:
        clauses.append("e.fecha >= ?")
        parameters.append(since)
    if until:
        clauses.append("e.fecha <= ?")
        parameters.append(until)
    with _connection(path) as connection:
        items: list[dict[str, Any]] = []
        matched_ids: list[int] = []
        scan_cursor = cursor_id
        has_more = False
        while len(items) <= limit:
            batch_clauses = list(clauses)
            batch_parameters = list(parameters)
            if scan_cursor is not None:
                batch_clauses.append("e.id < ?")
                batch_parameters.append(scan_cursor)
            batch_where = f"WHERE {' AND '.join(batch_clauses)}" if batch_clauses else ""
            batch_parameters.append(200)
            rows = connection.execute(
                f"""
                SELECT e.id AS _cursor_id, e.id_evento, e.tipo, e.app, e.remitente,
                       e.texto, e.texto_cifrado, e.riesgo, e.nivel_riesgo,
                       e.razones_riesgo, e.revision_estado, e.revisado_en,
                       e.direccion, e.duracion_s, e.fecha, e.recibido_en,
                       d.id AS dispositivo_id, d.nombre AS dispositivo
                FROM eventos AS e
                JOIN dispositivos AS d ON d.id = e.dispositivo_id
                {batch_where}
                ORDER BY e.id DESC
                LIMIT ?
                """,
                batch_parameters,
            ).fetchall()
            if not rows:
                break
            for row in rows:
                scan_cursor = int(row["_cursor_id"])
                item = _deserialize_event(row, encryption_key)
                if text is None or text.casefold() in (
                    (item.get("texto") or "") + " " + (item.get("remitente") or "")
                ).casefold():
                    if len(items) == limit:
                        has_more = True
                        break
                    item.pop("_cursor_id", None)
                    items.append(item)
                    matched_ids.append(scan_cursor)
            if has_more or len(rows) < 200:
                break

    next_cursor = str(matched_ids[-1]) if has_more and matched_ids else None
    return {"items": items, "next_cursor": next_cursor}


def query_review_queue(
    path: Path,
    encryption_key: str,
    *,
    reviewers_see_all: bool,
    full_access_consent_version: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    with _connection(path) as connection:
        if reviewers_see_all and full_access_consent_version:
            predicate = (
                "(d.consentimiento_version = ? OR "
                "(e.nivel_riesgo IN ('medio', 'alto') AND e.revision_estado IS NULL))"
            )
            parameters: tuple[Any, ...] = (full_access_consent_version, max(1, min(limit, 200)))
        else:
            predicate = "e.nivel_riesgo IN ('medio', 'alto') AND e.revision_estado IS NULL"
            parameters = (max(1, min(limit, 200)),)
        rows = connection.execute(
            f"""
            SELECT e.id, e.id_evento, e.dispositivo_id, e.tipo, e.app, e.remitente,
                   e.texto_cifrado, e.riesgo, e.nivel_riesgo, e.razones_riesgo,
                   e.revision_estado, e.fecha, e.recibido_en
            FROM eventos AS e
            JOIN dispositivos AS d ON d.id = e.dispositivo_id
            WHERE {predicate}
            ORDER BY e.id DESC LIMIT ?
            """,
            parameters,
        ).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            ciphertext = item.pop("texto_cifrado")
            item["texto"] = decrypt_text(ciphertext, encryption_key)
            item["razones_riesgo"] = json.loads(item.get("razones_riesgo") or "[]")
            context: list[dict[str, Any]] = []
            if item.get("remitente"):
                context_rows = connection.execute(
                    """
                    SELECT id_evento, texto_cifrado, fecha
                    FROM eventos
                    WHERE dispositivo_id = ? AND remitente = ? AND id < ?
                    ORDER BY id DESC LIMIT 3
                    """,
                    (item["dispositivo_id"], item["remitente"], item["id"]),
                ).fetchall()
                for context_row in context_rows:
                    context.append(
                        {
                            "id_evento": context_row["id_evento"],
                            "texto": decrypt_text(
                                context_row["texto_cifrado"],
                                encryption_key,
                            ),
                            "fecha": context_row["fecha"],
                        }
                    )
            item["contexto"] = context
            result.append(item)
    return result


def mark_event_review(
    path: Path,
    event_id: str,
    reviewer_id: int,
    status: str,
) -> tuple[bool, list[str]]:
    if status not in {"confirmado", "falso_positivo", "necesita_contacto"}:
        raise ValueError("Estado de revisión inválido.")
    reviewed_at = datetime.now(timezone.utc).isoformat()
    with _connection(path) as connection:
        row = connection.execute(
            "SELECT id FROM eventos WHERE id_evento = ?",
            (event_id,),
        ).fetchone()
        if not row:
            return False, []
        connection.execute(
            """
            UPDATE eventos SET revision_estado = ?, revisor_id = ?, revisado_en = ?
            WHERE id = ?
            """,
            (status, reviewer_id, reviewed_at, row["id"]),
        )
        rules = connection.execute(
            "SELECT regla_id FROM evento_reglas WHERE evento_id = ?",
            (row["id"],),
        ).fetchall()
    return True, [rule["regla_id"] for rule in rules]


def event_review_metadata(path: Path, event_id: str) -> dict[str, Any] | None:
    with _connection(path) as connection:
        row = connection.execute(
            """
            SELECT e.id_evento, e.dispositivo_id, e.nivel_riesgo, e.revision_estado,
                   d.consentimiento_version
            FROM eventos AS e
            JOIN dispositivos AS d ON d.id = e.dispositivo_id
            WHERE e.id_evento = ?
            """,
            (event_id,),
        ).fetchone()
    return dict(row) if row else None


def review_rule_statistics(path: Path) -> list[dict[str, Any]]:
    with _connection(path) as connection:
        rows = connection.execute(
            """
            SELECT er.regla_id, er.etiqueta,
                   COUNT(*) AS revisiones,
                   SUM(CASE WHEN e.revision_estado = 'confirmado' THEN 1 ELSE 0 END) AS confirmados,
                   SUM(CASE WHEN e.revision_estado = 'falso_positivo' THEN 1 ELSE 0 END) AS falsos_positivos,
                   SUM(CASE WHEN e.revision_estado = 'necesita_contacto' THEN 1 ELSE 0 END) AS sin_resolver
            FROM evento_reglas AS er
            JOIN eventos AS e ON e.id = er.evento_id
            WHERE e.revision_estado IS NOT NULL
            GROUP BY er.regla_id, er.etiqueta
            ORDER BY revisiones DESC, er.regla_id
            """
        ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        decided = item["confirmados"] + item["falsos_positivos"]
        item["precision"] = item["confirmados"] / decided if decided else None
        result.append(item)
    return result


def owner_event_updates(
    path: Path,
    device_id: str,
    encryption_key: str,
    limit: int = 100,
) -> list[dict[str, Any]]:
    result = query_events(
        path,
        encryption_key,
        device_id=device_id,
        limit=max(1, min(limit, 100)),
    )
    return result["items"]


def export_device_events(
    path: Path,
    device_id: str,
    encryption_key: str,
) -> list[dict[str, Any]]:
    with _connection(path) as connection:
        rows = connection.execute(
            """
            SELECT e.id, e.id_evento, e.dispositivo_id, e.tipo, e.app, e.remitente,
                   e.texto_cifrado, e.riesgo, e.nivel_riesgo, e.razones_riesgo,
                   e.revision_estado, e.revisado_en, e.fecha, e.recibido_en
            FROM eventos AS e WHERE e.dispositivo_id = ? ORDER BY e.id
            """,
            (device_id,),
        ).fetchall()
    return [_deserialize_event(row, encryption_key) for row in rows]


def delete_device_data(path: Path, device_id: str) -> int:
    with _connection(path) as connection:
        cursor = connection.execute(
            "DELETE FROM eventos WHERE dispositivo_id = ?",
            (device_id,),
        )
        connection.execute(
            "DELETE FROM dispositivos WHERE id = ?",
            (device_id,),
        )
        return cursor.rowcount


def review_updates_for_device(path: Path, device_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with _connection(path) as connection:
        rows = connection.execute(
            """
            SELECT id_evento, nivel_riesgo, revision_estado, revisado_en
            FROM eventos
            WHERE dispositivo_id = ? AND nivel_riesgo IN ('medio', 'alto')
              AND revision_estado IS NOT NULL
            ORDER BY revisado_en DESC LIMIT ?
            """,
            (device_id, max(1, min(limit, 100))),
        ).fetchall()
    return [dict(row) for row in rows]

