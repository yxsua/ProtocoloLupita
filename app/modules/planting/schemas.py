"""Esquemas Pydantic del módulo de siembra y atribución.

Intenta reutilizar ``app.core.schemas`` cuando exista (Plan 1), manteniendo
respaldo local compatible para ejecución y pruebas independientes.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

try:  # pragma: no cover - se activa cuando Plan 1 publique app/core/schemas.py
    from app.core.schemas import AttributionResult as CoreAttributionResult
except ImportError:  # pragma: no cover
    CoreAttributionResult = None


class AttributionResult(BaseModel):
    """Resultado de atribuir un número trampa receptor a una copia sembrada."""

    model_config = ConfigDict(extra="allow")

    trap_id: str
    copy_id: Optional[str] = None
    provider: Optional[str] = None
    seed_period: Optional[str] = None
    synthetic: bool = True
    attribution_id: Optional[str] = None
    manifest_hash: Optional[str] = None
    status: Literal["atribuido", "no_atribuido"] = "atribuido"
    trap_display: Optional[str] = None
    persona_alias: Optional[str] = None
    source_dataset: Optional[str] = None

    def to_core_contract(self) -> object:
        """Convierte al esquema compartido de ``app.core.schemas`` si existe."""
        if CoreAttributionResult is None:
            return self
        return CoreAttributionResult(
            trap_id=self.trap_id,
            copy_id=self.copy_id or "",
            provider=self.provider or "no_atribuido",
            seed_period=self.seed_period or "",
            synthetic=self.synthetic,
        )


class PersonaRecord(BaseModel):
    """Personaje sintético generado con Faker es_MX."""

    persona_id: str
    full_name: str
    alias: str
    municipality_code: str
    profile_note: str
    synthetic: bool = True


class SeedCopyRecord(BaseModel):
    """Copia sembrada asociada determinísticamente a un número trampa ficticio."""

    copy_id: str
    persona_id: str
    persona_alias: str
    provider: str
    dataset_name: str
    seed_period: str
    municipality_code: str = ""
    trap_id: str
    trap_display: str
    channel_scope: str = "call|sms"
    synthetic: bool = True
    created_at: str


class SeedBatchSummary(BaseModel):
    """Resumen del lote sembrado y su hash público de integridad."""

    seed_period: str
    total_copies: int
    manifest_hash: str
    synthetic: bool = True
    copies: list[SeedCopyRecord] = Field(default_factory=list)


class SeedBatchListItem(BaseModel):
    """Resumen seguro de un lote; no incluye los números trampa asignados."""

    seed_period: str
    total_copies: int
    manifest_hash: str
    updated_at: str
    synthetic: bool = True
