"""Adaptadores de integración y fábrica opcional de router FastAPI."""

from __future__ import annotations

from typing import Any, Optional

from app.modules.intel.extractors import extract_indicators
from app.modules.intel.service import IntelEngine, get_default_engine
from app.modules.intel.validators import verify_account


def handle_process_event(
    payload: dict[str, Any],
    engine: Optional[IntelEngine] = None,
) -> dict[str, Any]:
    """Adaptador puro para procesar un evento y retornar JSON serializable."""
    target = engine or get_default_engine()
    return target.process_event(payload).to_dict()


def handle_extract_indicators(
    text: str,
    channel: str = "call",
) -> list[dict[str, Any]]:
    """Adaptador puro para extraer indicadores normalizados sin persistir evento."""
    return [ind.to_dict() for ind in extract_indicators(text, channel=channel)]


def handle_verify_account(value: str, kind: str) -> dict[str, Any]:
    """Adaptador puro para validar CLABE o tarjeta."""
    return verify_account(value, kind).to_dict()


def handle_lookup_indicator(
    query: str,
    engine: Optional[IntelEngine] = None,
) -> dict[str, Any]:
    """Adaptador puro para consulta del Verificador ciudadano."""
    target = engine or get_default_engine()
    return target.lookup_indicator(query).to_dict()


def handle_list_campaigns(engine: Optional[IntelEngine] = None) -> list[dict[str, Any]]:
    """Lista las campañas consolidadas para tablero o portal."""
    target = engine or get_default_engine()
    return [camp.to_dict() for camp in target.list_campaigns()]


def handle_get_campaign(
    campaign_id: str,
    engine: Optional[IntelEngine] = None,
) -> Optional[dict[str, Any]]:
    """Obtiene detalle de una campaña."""
    target = engine or get_default_engine()
    summary = target.get_campaign(campaign_id)
    return summary.to_dict() if summary is not None else None


def handle_get_bulletin(engine: Optional[IntelEngine] = None) -> dict[str, Any]:
    """Obtiene el boletín epidemiológico semanal de campañas activas."""
    target = engine or get_default_engine()
    return target.get_epidemiological_bulletin()


def handle_get_authority_package(
    campaign_id: str,
    engine: Optional[IntelEngine] = None,
) -> Optional[dict[str, Any]]:
    """Obtiene el paquete simulado para Fiscalía / UIF / Policía Cibernética."""
    target = engine or get_default_engine()
    return target.get_authority_package(campaign_id)


def handle_get_brand_notice(
    campaign_id: str,
    engine: Optional[IntelEngine] = None,
) -> Optional[dict[str, Any]]:
    """Obtiene el aviso simulado para institución suplantada."""
    target = engine or get_default_engine()
    return target.get_impersonated_brand_notice(campaign_id)


def handle_verify_evidence(engine: Optional[IntelEngine] = None) -> dict[str, Any]:
    """Verifica la integridad de la cadena de hashes de evidencia."""
    target = engine or get_default_engine()
    return target.verify_evidence_integrity().to_dict()


def create_fastapi_router(engine: Optional[IntelEngine] = None) -> Any:
    """Construye un APIRouter de FastAPI bajo demanda sin acoplar el núcleo a FastAPI."""
    from fastapi import APIRouter, HTTPException  # type: ignore[import-not-found]

    router = APIRouter(prefix="/intel", tags=["intel"])

    @router.post("/events")
    def process_event_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return handle_process_event(payload, engine=engine)

    @router.post("/verify-account")
    def verify_account_endpoint(payload: dict[str, Any]) -> dict[str, Any]:
        return handle_verify_account(
            value=str(payload.get("value", "")),
            kind=str(payload.get("kind", "clabe")),
        )

    @router.get("/lookup")
    def lookup_endpoint(q: str) -> dict[str, Any]:
        return handle_lookup_indicator(q, engine=engine)

    @router.get("/campaigns")
    def campaigns_endpoint() -> list[dict[str, Any]]:
        return handle_list_campaigns(engine=engine)

    @router.get("/campaigns/{campaign_id}")
    def campaign_detail_endpoint(campaign_id: str) -> dict[str, Any]:
        camp = handle_get_campaign(campaign_id, engine=engine)
        if camp is None:
            raise HTTPException(status_code=404, detail="Campaña no encontrada")
        return camp

    @router.get("/bulletin")
    def bulletin_endpoint() -> dict[str, Any]:
        return handle_get_bulletin(engine=engine)

    @router.get("/campaigns/{campaign_id}/authority-package")
    def authority_package_endpoint(campaign_id: str) -> dict[str, Any]:
        pkg = handle_get_authority_package(campaign_id, engine=engine)
        if pkg is None:
            raise HTTPException(status_code=404, detail="Campaña no encontrada")
        return pkg

    @router.get("/campaigns/{campaign_id}/brand-notice")
    def brand_notice_endpoint(campaign_id: str) -> dict[str, Any]:
        notice = handle_get_brand_notice(campaign_id, engine=engine)
        if notice is None:
            raise HTTPException(status_code=404, detail="Campaña no encontrada")
        return notice

    @router.get("/evidence/verify")
    def verify_evidence_endpoint() -> dict[str, Any]:
        return handle_verify_evidence(engine=engine)

    return router
