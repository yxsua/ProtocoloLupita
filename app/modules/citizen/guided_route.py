"""Rutas guiadas locales en lenguaje claro segun entidad, canal y nivel de verificacion."""

from __future__ import annotations

from app.modules.sms.schemas import GuidedRoute, GuidedStep, VerificationStatus

_OFFICIAL_CHANNELS: dict[str, tuple[str, str]] = {
    "SAT": (
        "Portal oficial del SAT (escribir sat.gob.mx manualmente) o MarcaSAT 55 627 22 728",
        "Nunca regularices multas desde enlaces recibidos por SMS; entra escribiendo sat.gob.mx en tu navegador.",
    ),
    "IMSS": (
        "Portal imss.gob.mx o app IMSS Digital / 800 623 2323",
        "El IMSS no solicita pagos ni datos bancarios por enlaces de texto.",
    ),
    "CFE": (
        "App CFE Contigo, cfe.mx o telefono 071",
        "Consulta tu recibo directamente en cfe.mx o marcando al 071 antes de realizar cualquier pago.",
    ),
    "banco": (
        "Telefono impreso al reverso de tu tarjeta fisica o app oficial bancaria",
        "No marques telefonos incluidos en el SMS ni compartas codigos token o NIP.",
    ),
    "paqueteria": (
        "Sitio oficial de la mensajeria escribiendo la direccion manualmente (sin acortadores)",
        "Desconfia de cobros pequenos por aduana o liberacion de paquetes mediante enlaces acortados.",
    ),
    "telefonica": (
        "App oficial de tu compania o centro de atencion desde tu linea",
        "No abras acortadores que prometen bonos o advierten suspension inmediata.",
    ),
}


def build_guided_route(
    *,
    impersonated_entity: str,
    channel: str,
    verification_status: VerificationStatus,
    rate_limited: bool = False,
) -> GuidedRoute:
    """Construye una ruta de proteccion y denuncia local comprensible."""
    official_channel, entity_tip = _OFFICIAL_CHANNELS.get(
        impersonated_entity,
        (
            "Canales oficiales de la institucion (buscados manualmente) y denuncia anonima 089",
            "Verifica directamente con la institucion o comercio por un medio oficial independiente.",
        ),
    )

    do_not_actions = [
        "No abras enlaces desactivados (hxxp) ni acortadores incluidos en el mensaje.",
        "No respondas el SMS ni devuelvas llamadas al numero que te contacto.",
        "No compartas codigos SMS, NIP, token, CURP ni deposites a cuentas desconocidas.",
    ]

    if verification_status == "campana_corroborada":
        summary = (
            "Ruta prioritaria de proteccion: este indicador coincide con una campaña corroborada "
            "en el motor de inteligencia."
        )
    elif verification_status == "indicio":
        summary = (
            "Ruta preventiva: se detectaron indicios de riesgo pendientes de corroboracion adicional."
        )
    else:
        summary = (
            "Ruta informativa de precaucion: el reporte permanece sin verificar; conserva evidencia "
            "sin interactuar con el remitente."
        )

    if rate_limited:
        summary += " Se aplico limite de tasa por reportes repetidos; evita reenviar el mismo reporte."

    steps = [
        GuidedStep(
            order=1,
            title="Aisla el mensaje sin interactuar",
            detail="Conserva una captura para evidencia y bloquea el numero remitente en tu telefono.",
        ),
        GuidedStep(
            order=2,
            title="Verifica por canal oficial escrito manualmente",
            detail=entity_tip,
            official_channel=official_channel,
        ),
        GuidedStep(
            order=3,
            title="Reporta ante autoridades si hubo intento de fraude o cargo",
            detail=(
                "Si recibiste llamada o SMS de extorsion/suplantacion, reporta al 089 (denuncia anonima) "
                "o ante la Guardia Nacional (Cert-MX). Para temas bancarios acude a CONDUSEF."
            ),
            official_channel="089 (Denuncia anonima) · Guardia Nacional 088 · CONDUSEF 55 5340 0999",
        ),
    ]

    if channel == "llamada":
        steps[0] = GuidedStep(
            order=1,
            title="Cuelga y no devuelvas la llamada",
            detail="Anota la hora y el numero visible sin proporcionar datos personales ni codigos.",
        )

    return GuidedRoute(summary=summary, do_not_actions=do_not_actions, steps=steps)
