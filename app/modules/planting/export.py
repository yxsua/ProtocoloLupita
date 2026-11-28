"""Exporta copias SQLite sintéticas aisladas para demostraciones controladas."""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from app.modules.planting.fixtures_local import QUERETARO_MUNICIPALITIES
from app.modules.planting.schemas import SeedCopyRecord


def _municipality_name(code: str) -> str:
    return next(
        (item["municipality_name"] for item in QUERETARO_MUNICIPALITIES if item["municipality_code"] == code),
        "Querétaro",
    )


def build_seed_archive(seed_period: str, copies: list[SeedCopyRecord]) -> tuple[bytes, str]:
    """Devuelve un ZIP con una base por copia y un manifiesto sin números trampa."""
    if not copies:
        raise ValueError("El lote no contiene copias para exportar.")

    output = io.BytesIO()
    manifest: dict[str, object] = {
        "seed_period": seed_period,
        "synthetic": True,
        "copies": [],
    }

    with tempfile.TemporaryDirectory(prefix="lupita-seed-") as temp_dir:
        root = Path(temp_dir)
        source_path = root / "base_sintetica.sqlite3"
        with sqlite3.connect(source_path) as db:
            db.executescript(
                """
                CREATE TABLE synthetic_records (
                    record_id INTEGER PRIMARY KEY,
                    nombre TEXT NOT NULL,
                    municipio TEXT NOT NULL,
                    dataset TEXT NOT NULL,
                    telefono TEXT,
                    synthetic INTEGER NOT NULL CHECK (synthetic = 1)
                );
                """
            )
            db.executemany(
                "INSERT INTO synthetic_records (nombre, municipio, dataset, telefono, synthetic) VALUES (?, ?, ?, NULL, 1)",
                [
                    (f"Registro sintético {i:03d}", _municipality_name("22014"), "base demostrativa")
                    for i in range(1, 11)
                ],
            )

        archive_entries: list[tuple[str, bytes]] = []
        for index, copy in enumerate(copies, start=1):
            filename = f"copia_{index:03d}.sqlite3"
            copy_path = root / filename
            shutil.copyfile(source_path, copy_path)
            with sqlite3.connect(copy_path) as db:
                db.execute(
                    "INSERT INTO synthetic_records (nombre, municipio, dataset, telefono, synthetic) VALUES (?, ?, ?, ?, 1)",
                    (
                        copy.persona_alias,
                        _municipality_name(copy.municipality_code),
                        copy.dataset_name,
                        copy.trap_id,
                    ),
                )
            file_bytes = copy_path.read_bytes()
            file_hash = hashlib.sha256(file_bytes).hexdigest()
            archive_entries.append((filename, file_bytes))
            manifest["copies"].append(
                {
                    "file": filename,
                    "copy_id": copy.copy_id,
                    "provider": copy.provider,
                    "dataset": copy.dataset_name,
                    "sha256": file_hash,
                    "synthetic": True,
                }
            )

        readme = (
            "COPIAS DE PRUEBA — PROTOCOLO LUPITA\n\n"
            "Todos los registros, nombres, municipios y teléfonos de estas bases son ficticios.\n"
            "No contienen información personal real y no deben conectarse a servicios productivos.\n"
            "Cada archivo tiene un identificador sintético único para atribución de la demostración.\n"
            "Distribuya a cada participante únicamente el archivo que le fue asignado; no comparta\n"
            "el paquete completo ni el registro privado de atribución.\n"
        ).encode("utf-8")
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("LEEME.txt", readme)
            archive.writestr("lote.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for filename, file_bytes in archive_entries:
                archive.writestr(filename, file_bytes)

    safe_period = re.sub(r"[^A-Za-z0-9_-]", "_", seed_period)
    return output.getvalue(), f"copias_sinteticas_{safe_period}.zip"
