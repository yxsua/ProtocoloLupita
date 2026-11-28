from __future__ import annotations

import hashlib
from typing import Any


def consent_text(settings: Any) -> str:
    reviewer_scope = (
        "Los revisores autorizados podrán ver todos los mensajes del teléfono."
        if settings.reviewers_see_all
        else "Los revisores autorizados solo podrán ver mensajes marcados como posibles alertas y hasta tres mensajes previos del mismo remitente."
    )
    return (
        "Los administradores autorizados gestionan el dispositivo y la configuración. "
        + reviewer_scope
        + f" Los textos sin alerta se eliminan después de {settings.retention_text_hours} horas; "
        + f"las alertas se conservan hasta {settings.retention_alert_days} días. "
        + "Puedes retirar el consentimiento pausando o desvinculando el teléfono. "
        + "Para desinstalar, desactiva el monitoreo, desvincula y elimina la app desde Ajustes de Android."
    )


def consent_version(settings: Any) -> str:
    return hashlib.sha256(consent_text(settings).encode("utf-8")).hexdigest()[:32]
