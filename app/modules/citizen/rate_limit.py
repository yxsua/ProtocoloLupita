"""Control de limite de tasa para reportes ciudadanos repetidos."""

from __future__ import annotations

from collections import defaultdict, deque
import time

from app.modules.citizen.schemas import ReportInput


class RateLimiter:
    """Ventana deslizante en memoria sobre huella anonima + indicador/negocio objetivo."""

    def __init__(self, *, max_reports: int = 2, window_seconds: int = 600) -> None:
        self.max_reports = max_reports
        self.window_seconds = window_seconds
        self._buckets: dict[str, deque[float]] = defaultdict(deque)

    def _build_key(self, report: ReportInput) -> str:
        target = (
            (report.reported_business_name or "").strip().lower()
            or (report.indicators.domains[0] if report.indicators.domains else "")
            or (report.indicators.phones[0] if report.indicators.phones else "")
            or (report.indicators.accounts[0] if report.indicators.accounts else "")
            or (report.indicators.senders[0].lower() if report.indicators.senders else "")
            or report.municipality.lower()
        )
        return f"{report.fingerprint_hash}:{target}"

    def check_and_record(self, report: ReportInput, *, now: float | None = None) -> bool:
        """Devuelve True si el reporte excede el limite de tasa."""
        ts = time.monotonic() if now is None else float(now)
        key = self._build_key(report)
        bucket = self._buckets[key]
        cutoff = ts - self.window_seconds

        while bucket and bucket[0] < cutoff:
            bucket.popleft()

        if len(bucket) >= self.max_reports:
            bucket.append(ts)
            return True

        bucket.append(ts)
        return False

    def reset(self) -> None:
        """Limpia el estado interno (util entre pruebas)."""
        self._buckets.clear()
