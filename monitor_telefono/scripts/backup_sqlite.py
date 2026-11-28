from __future__ import annotations

import os
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote


def main() -> None:
    source_path = Path(os.environ.get("DATABASE_PATH", "/data/monitor.sqlite3"))
    backup_dir = Path(os.environ.get("BACKUP_DIR", "/backups"))
    retention_days = int(os.environ.get("BACKUP_RETENTION_DAYS", "30"))
    if retention_days < 1:
        raise ValueError("BACKUP_RETENTION_DAYS debe ser al menos 1.")
    if not source_path.is_file():
        raise FileNotFoundError(f"No existe la base SQLite: {source_path}")

    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination_path = backup_dir / f"monitor-{stamp}.sqlite3"
    uri = f"file:{quote(str(source_path.resolve()))}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as source:
        with closing(sqlite3.connect(destination_path, timeout=30)) as destination:
            source.backup(destination)
            destination.commit()
    os.chmod(destination_path, 0o600)

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    for candidate in backup_dir.glob("monitor-*.sqlite3"):
        if candidate == destination_path:
            continue
        modified = datetime.fromtimestamp(candidate.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            candidate.unlink()


if __name__ == "__main__":
    main()
