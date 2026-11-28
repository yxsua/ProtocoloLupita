"""Adaptador de agregados municipales hacia el mapa de Integrante 2."""

from __future__ import annotations

from collections import defaultdict
from typing import Protocol

from app.modules.citizen.schemas import MapAggregateResponse, MunicipalAggregate


class MapPort(Protocol):
    """Contrato hacia el modulo de mapa/tablero (solo municipio y conteo que cumple umbral)."""

    def record_report(self, municipality: str, *, rate_limited: bool = False) -> None:
        ...

    def get_map_aggregates(self) -> MapAggregateResponse:
        ...


class MunicipalMapAdapter:
    """Agrega conteos por municipio respetando el umbral minimo de privacidad."""

    def __init__(self, *, threshold: int = 5) -> None:
        self.threshold = threshold
        self._counts_by_key: dict[str, int] = defaultdict(int)
        self._display_names: dict[str, str] = {}
        self._total_reports = 0

    @staticmethod
    def _normalize_key(municipality: str) -> tuple[str, str]:
        cleaned = " ".join((municipality or "").strip().split())
        if not cleaned:
            return "no especificado", "No especificado"
        return cleaned.lower(), cleaned

    def record_report(self, municipality: str, *, rate_limited: bool = False) -> None:
        """Registra un reporte en el agregado. Los limitados por tasa no inflan el mapa."""
        if rate_limited:
            return
        key, label = self._normalize_key(municipality)
        self._display_names.setdefault(key, label)
        self._counts_by_key[key] += 1
        self._total_reports += 1

    def get_map_aggregates(self) -> MapAggregateResponse:
        """Publica solo municipios con count >= threshold y conserva el total agregado."""
        visible: list[MunicipalAggregate] = []
        hidden_count = 0

        for key, count in self._counts_by_key.items():
            if count >= self.threshold:
                visible.append(
                    MunicipalAggregate(
                        municipality=self._display_names[key],
                        count=count,
                    )
                )
            else:
                hidden_count += 1

        visible.sort(key=lambda item: (-item.count, item.municipality.lower()))
        return MapAggregateResponse(
            threshold=self.threshold,
            visible_municipalities=visible,
            total_reports=self._total_reports,
            hidden_municipalities_count=hidden_count,
        )

    def reset(self) -> None:
        """Reinicia contadores locales (util para pruebas)."""
        self._counts_by_key.clear()
        self._display_names.clear()
        self._total_reports = 0
