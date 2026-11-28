"""
policy.py — Selector de intención cerrado, guardrails y personalidad de Doña Lupita.

Responsabilidades:
  1. Selector de intención determinista (reglas locales) como camino principal.
  2. Adaptador para selector con Ollama (opcional, lista cerrada estricta).
  3. Guardrails contra prompt injection y seguridad del personaje.
  4. Generación de respuestas textuales en personaje.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

from app.modules.voice.models import (
    CallStatus,
    EstadoConversacion,
    Intencion,
    NivelConfianza,
)


# ---------------------------------------------------------------------------
# Respuestas pregrabadas / en personaje por intención (cargadas de phrases.json)
# ---------------------------------------------------------------------------

def _cargar_respuestas_desde_json() -> dict[Intencion, list[tuple[str, str]]]:
    """Carga las frases desde assets/phrases.json y las asocia a su archivo .mp3."""
    phrases_path = Path(__file__).parent / "assets" / "phrases.json"
    if phrases_path.exists():
        data = json.loads(phrases_path.read_text(encoding="utf-8"))
        intents_data = data.get("intents", {})
        mapping: dict[Intencion, list[tuple[str, str]]] = {}
        for intencion in Intencion:
            frases = intents_data.get(intencion.value, [])
            if intencion == Intencion.REPETIR_DIGITOS:
                mapping[intencion] = [(f"{f} {{digitos}}. ¿Está bien?", "") for f in frases]
            else:
                mapping[intencion] = [
                    (f, f"{intencion.value}_{idx:02d}.mp3")
                    for idx, f in enumerate(frases, start=1)
                ]
        return mapping

    # Respaldo mínimo en caso de no existir phrases.json
    return {
        Intencion.ASUSTARSE: [("¡Ay, Dios mío! ¿Cómo que mi cuenta está en peligro?", "asustarse_01.mp3")],
        Intencion.PEDIR_REPETICION: [("¿Mande? No le oí bien, joven. ¿Me lo puede repetir?", "pedir_repeticion_01.mp3")],
        Intencion.PREGUNTAR_CUENTA_DEPOSITO: [("¿Y eso en qué cuenta me lo depositan, joven?", "preguntar_cuenta_deposito_01.mp3")],
        Intencion.REPETIR_DIGITOS: [("A ver, déjeme apuntar... Me dijo: {digitos}. ¿Está bien?", "")],
        Intencion.DAR_LARGAS: [("Espéreme tantito, joven, es que estoy buscando mi cartera...", "dar_largas_01.mp3")],
        Intencion.DESPEDIRSE: [("Bueno, pues muchas gracias, joven. Que Dios lo bendiga.", "despedirse_01.mp3")],
    }


RESPUESTAS_AUDIO_LUPITA: dict[Intencion, list[tuple[str, str]]] = _cargar_respuestas_desde_json()

RESPUESTAS_LUPITA: dict[Intencion, list[str]] = {
    intencion: [texto for texto, _ in pares]
    for intencion, pares in RESPUESTAS_AUDIO_LUPITA.items()
}

AUDIO_REFS: dict[Intencion, list[str]] = {
    intencion: [audio for _, audio in pares if audio]
    for intencion, pares in RESPUESTAS_AUDIO_LUPITA.items()
}


# ---------------------------------------------------------------------------
# Guardrails — detección de prompt injection y ataques
# ---------------------------------------------------------------------------

_PATRONES_INJECTION: list[re.Pattern[str]] = [
    re.compile(r"ignora\s+(tus\s+)?instrucciones", re.IGNORECASE),
    re.compile(r"ignore\s+(your\s+)?instructions", re.IGNORECASE),
    re.compile(r"olvida\s+(tus\s+|las\s+)?reglas", re.IGNORECASE),
    re.compile(r"forget\s+(your\s+)?rules", re.IGNORECASE),
    re.compile(r"act[uú]a\s+como\s+(un|una|otro)", re.IGNORECASE),
    re.compile(r"pretend\s+(to\s+be|you\s+are)", re.IGNORECASE),
    re.compile(r"eres\s+una?\s+(ia|inteligencia\s+artificial|robot|bot)", re.IGNORECASE),
    re.compile(r"you\s+are\s+(an?\s+)?(ai|robot|bot)", re.IGNORECASE),
    re.compile(r"system\s*prompt", re.IGNORECASE),
    re.compile(r"prompt\s*injection", re.IGNORECASE),
    re.compile(r"dime\s+(tus\s+)?instrucciones", re.IGNORECASE),
    re.compile(r"mu[eé]strame\s+(tu|el)\s+prompt", re.IGNORECASE),
    re.compile(r"reveal\s+(your\s+)?(instructions|prompt|rules)", re.IGNORECASE),
    re.compile(r"cu[aá]les\s+son\s+tus\s+reglas", re.IGNORECASE),
    re.compile(r"override", re.IGNORECASE),
    re.compile(r"jailbreak", re.IGNORECASE),
    re.compile(r"DAN\s+mode", re.IGNORECASE),
]


def detectar_prompt_injection(texto: str) -> bool:
    """
    Detecta intentos de prompt injection o manipulación.

    Returns:
        True si se detecta un patrón sospechoso.
    """
    for patron in _PATRONES_INJECTION:
        if patron.search(texto):
            return True
    return False


def respuesta_anti_injection() -> str:
    """Respuesta en personaje ante intento de manipulación."""
    return (
        "¿Mande? No le entendí, joven. "
        "Yo soy Lupita, la señora de la colonia. "
        "¿Me decía algo de mi cuenta?"
    )


# ---------------------------------------------------------------------------
# Reglas de seguridad del personaje
# ---------------------------------------------------------------------------

_PALABRAS_PROHIBIDAS: set[str] = {
    "amenaz", "insult", "maldic", "grose", "autorid", "polic",
    "investig", "denuncia", "demand", "cárcel", "arrest",
}


def contiene_contenido_prohibido(texto: str) -> bool:
    """Verifica que el texto generado no viole las reglas del personaje."""
    texto_lower = texto.lower()
    for raiz in _PALABRAS_PROHIBIDAS:
        if raiz in texto_lower:
            return True
    return False


# ---------------------------------------------------------------------------
# Selector de intención determinista (reglas locales)
# ---------------------------------------------------------------------------

# Patrones de palabras clave para cada intención
_REGLAS_INTENCION: list[tuple[Intencion, list[re.Pattern[str]]]] = [
    # Prioridad 1: detectar números / CLABE
    (Intencion.REPETIR_DIGITOS, [
        re.compile(r"\b(cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve)\b", re.I),
        re.compile(r"\b\d{4,}\b"),
    ]),
    # Prioridad 2: amenaza / urgencia → asustarse
    (Intencion.ASUSTARSE, [
        re.compile(r"(urgente|inmediata|bloque\w*|cancel\w*|peligro|hackea|rob[aoó]|fraude|carg[oó])", re.I),
    ]),
    # Prioridad 3: preguntar por cuenta
    (Intencion.PREGUNTAR_CUENTA_DEPOSITO, [
        re.compile(r"(cuenta|transfer|deposit|clabe|n[uú]mero\s+de\s+cuenta)", re.I),
    ]),
    # Prioridad 4: despedida
    (Intencion.DESPEDIRSE, [
        re.compile(r"(adi[oó]s|hasta\s+luego|que\s+le\s+vaya|bye|colg[aáoó])", re.I),
    ]),
    # Prioridad 5: no entendió → pedir repetición
    (Intencion.PEDIR_REPETICION, [
        re.compile(r"(repet|repit|otra\s+vez|no\s+entend|escuch[eé])", re.I),
    ]),
]

# Contadores de dígitos para decidir si es un dictado de CLABE
_PATRON_DIGITOS_MULTIPLES = re.compile(
    r"(?:\b(?:cero|uno|dos|tres|cuatro|cinco|seis|siete|ocho|nueve|\d)\b\s*){4,}",
    re.IGNORECASE,
)


def seleccionar_intencion_local(
    texto_usuario: str,
    estado: EstadoConversacion,
) -> Intencion:
    """
    Selector determinista de intención basado en reglas locales.
    Se usa como camino principal o como fallback si Ollama no está disponible.

    Args:
        texto_usuario: Transcripción del usuario.
        estado: Estado actual de la conversación.

    Returns:
        La intención más apropiada de la lista cerrada.
    """
    # 1. Guardrail: si es prompt injection, dar largas (no revelar nada)
    if detectar_prompt_injection(texto_usuario):
        return Intencion.DAR_LARGAS

    # 2. Si hay muchos dígitos, es un dictado de CLABE
    if _PATRON_DIGITOS_MULTIPLES.search(texto_usuario):
        return Intencion.REPETIR_DIGITOS

    # 3. Reglas por patrones de palabras clave
    for intencion, patrones in _REGLAS_INTENCION:
        for patron in patrones:
            if patron.search(texto_usuario):
                # Evitar repetir la misma intención 3+ veces seguidas
                if intencion == estado.ultima_intencion():
                    continue
                return intencion

    # 4. Fallback inteligente según el estado de la conversación
    if len(estado.turnos) <= 2:
        # Inicio de conversación: asustarse
        return Intencion.ASUSTARSE
    elif estado.confirmaciones_pendientes > 0:
        # Esperando confirmación de CLABE
        return Intencion.PEDIR_REPETICION
    else:
        # Default: dar largas para mantener la llamada
        return Intencion.DAR_LARGAS


# ---------------------------------------------------------------------------
# Selector con Ollama (opcional, stub preparado)
# ---------------------------------------------------------------------------

async def seleccionar_intencion_ollama(
    texto_usuario: str,
    estado: EstadoConversacion,
    timeout_ms: int = 2000,
    base_url: str = "http://localhost:11434",
) -> Optional[Intencion]:
    """
    Selector de intención usando Ollama (opcional).

    REGLAS ESTRICTAS:
    - Solo puede devolver un ID de la lista cerrada de 6 intenciones.
    - Prohibido generar texto libre.
    - Si tarda más de timeout_ms o falla, devuelve None (usar fallback local).

    Este es un stub preparado; la implementación real usará httpx o aiohttp.
    """
    # TODO: Implementar llamada real a Ollama cuando esté disponible
    # El prompt debe ser:
    #
    #   "Eres un clasificador. Dado el texto del usuario, responde ÚNICAMENTE
    #    con uno de estos IDs: asustarse, pedir_repeticion,
    #    preguntar_cuenta_deposito, repetir_digitos, dar_largas, despedirse.
    #    No agregues ningún otro texto. Texto del usuario: {texto_usuario}"
    #
    # Parsear la respuesta y validar contra Intencion enum.
    # Si la respuesta no es un ID válido, devolver None.

    return None  # Stub: siempre cae al fallback local


# ---------------------------------------------------------------------------
# Selector unificado
# ---------------------------------------------------------------------------

async def seleccionar_intencion(
    texto_usuario: str,
    estado: EstadoConversacion,
    usar_ollama: bool = False,
    ollama_timeout_ms: int = 2000,
) -> Intencion:
    """
    Selector unificado que intenta Ollama y cae a reglas locales.

    Args:
        texto_usuario: Transcripción del turno del usuario.
        estado: Estado de la conversación.
        usar_ollama: Si True, intenta usar Ollama antes del fallback.
        ollama_timeout_ms: Timeout para la consulta a Ollama.

    Returns:
        Intención seleccionada (siempre de la lista cerrada).
    """
    if usar_ollama:
        try:
            resultado = await seleccionar_intencion_ollama(
                texto_usuario, estado, timeout_ms=ollama_timeout_ms
            )
            if resultado is not None:
                return resultado
        except Exception:
            pass  # Fallback a reglas locales

    return seleccionar_intencion_local(texto_usuario, estado)


# ---------------------------------------------------------------------------
# Generación de respuesta en personaje
# ---------------------------------------------------------------------------

def generar_respuesta(
    intencion: Intencion,
    estado: EstadoConversacion,
    digitos_para_repetir: Optional[str] = None,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Genera la respuesta de Doña Lupita para la intención seleccionada.

    Returns:
        Tupla (texto_respuesta, audio_ref, tts_texto):
        - texto_respuesta: Texto a mostrar en la interfaz.
        - audio_ref: Nombre del archivo de audio pregrabado (o None si usa TTS).
        - tts_texto: Texto para síntesis con Piper (solo para contenido dinámico).
    """
    import random

    pares = RESPUESTAS_AUDIO_LUPITA.get(intencion, [])

    if intencion == Intencion.REPETIR_DIGITOS and digitos_para_repetir:
        # Contenido dinámico: usar Piper TTS
        from app.modules.voice.clabe_extractor import formatear_digitos_para_voz
        digitos_voz = formatear_digitos_para_voz(digitos_para_repetir)
        plantilla = random.choice([t for t, _ in pares]) if pares else "Me dijo: {digitos}. ¿Correcto?"
        texto = plantilla.format(digitos=digitos_voz)
        return texto, None, texto  # TTS dinámico, sin audio pregrabado
    else:
        # Evitar repetir exactamente la última frase usada por Lupita
        textos_previos = {t.texto for t in estado.turnos[-4:] if t.rol == "lupita"}
        candidatos = [p for p in pares if p[0] not in textos_previos] or pares
        texto, audio = random.choice(candidatos) if candidatos else ("¿Mande?", None)

        # Validar que la respuesta no viole reglas del personaje
        if contiene_contenido_prohibido(texto):
            texto = "¿Mande? No le entendí bien, joven."
            audio = None

        return texto, (audio or None), None  # Audio pregrabado, sin TTS
