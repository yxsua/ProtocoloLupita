"""
router.py — Endpoints FastAPI para el módulo de voz (Doña Lupita).

Proporciona:
  - GET  /voice/                 → Página con Llamada Manual y Simulación Automática
  - POST /voice/start            → Iniciar sesión de llamada manual
  - POST /voice/transcribe       → Transcribir audio con Whisper en memoria (sin guardar audio crudo)
  - POST /voice/process          → Procesar turno manual (texto o audio)
  - POST /voice/hangup           → Colgar la llamada manual
  - GET  /voice/bot/scenarios    → Listar escenarios E01-E08 disponibles
  - POST /voice/bot/start        → Iniciar simulación Bot Estafador vs. Doña Lupita
  - POST /voice/bot/next         → Ejecutar el siguiente turno automático y acotado
  - POST /voice/bot/stop         → Detener simulación automática
  - GET  /voice/status           → Estado del motor de audio
  - GET  /voice/audio/{filename} → Servir fragmentos pregrabados (.mp3 / .wav)
"""

from __future__ import annotations

import base64
import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.modules.voice.audio_engine import AudioEngine
from app.modules.voice.models import AvatarId, CallResult, LockedVoiceProfile
from app.modules.voice.service import (
    BotEstafadorSimulator,
    DEFAULT_BOT_MAX_TURNS,
    VoiceService,
    cargar_escenarios_voz,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "voice"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

_ASSETS_DIR = Path(__file__).parent / "assets"
_MAX_AUDIO_BYTES = 15 * 1024 * 1024

# Sesiones activas en memoria
_sessions: dict[str, VoiceService] = {}
_bot_sessions: dict[str, BotEstafadorSimulator] = {}
_shared_engine: Optional[AudioEngine] = None


def _get_or_create_engine() -> AudioEngine:
    """Reutiliza el AudioEngine web para no recargar Whisper/Piper por petición."""
    global _shared_engine
    if _shared_engine is None:
        _shared_engine = AudioEngine.for_web(assets_dir=str(_ASSETS_DIR))
    return _shared_engine


def _get_session(session_id: str) -> Optional[VoiceService]:
    return _sessions.get(session_id)


# -----------------------------------------------------------------------
# Vista principal
# -----------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def voice_page(request: Request):
    """Página principal de la interfaz de llamada (Manual + Bot Estafador)."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "title": "Protocolo Lupita — Voz Híbrida y Simulador",
            "scenarios": cargar_escenarios_voz(),
        },
    )


# -----------------------------------------------------------------------
# Apartado A: Llamada Manual
# -----------------------------------------------------------------------

@router.post("/start")
async def start_call(
    max_duration: float = Form(default=300.0, ge=30.0, le=600.0),
    trap_id: Optional[str] = Form(default=None),
    locked_avatar: AvatarId = Form(default=AvatarId.LUPITA),
    locked_voice_profile: str = Form(default=""),
):
    """Inicia una nueva sesión de llamada manual."""
    session_id = uuid.uuid4().hex[:12]
    engine = _get_or_create_engine()

    service = VoiceService(
        max_duration_seconds=max_duration,
        audio_engine=engine,
        trap_id=trap_id,
        locked_avatar=locked_avatar,
        locked_voice_profile=_parse_locked_voice_profile(locked_voice_profile),
    )
    result = service.iniciar_llamada()
    _sessions[session_id] = service

    logger.info(f"[Router] Sesión manual iniciada: {session_id}")
    response_data = await _build_turn_response(service, result, "")
    response_data.update({
        "session_id": session_id,
        "audio_status": engine.status(),
    })
    return JSONResponse(content=response_data)


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
):
    """
    Transcribe audio del micrófono en memoria usando Whisper local.
    Regla de seguridad: el audio crudo se descarta inmediatamente y nunca se persiste.
    """
    engine = _get_or_create_engine()
    audio_bytes = await audio.read(_MAX_AUDIO_BYTES + 1)
    if len(audio_bytes) > _MAX_AUDIO_BYTES:
        del audio_bytes
        raise HTTPException(status_code=413, detail="El audio excede el límite de 15 MB.")
    text = ""
    source = "whisper" if engine.whisper_disponible else "unavailable"

    try:
        if audio_bytes and engine.whisper_disponible:
            text = await engine.transcribir_o_leer_texto(audio_bytes)
    finally:
        # Descartar audio crudo explícitamente de memoria
        del audio_bytes

    return JSONResponse(content={
        "text": text.strip(),
        "source": source,
        "whisper_available": engine.whisper_disponible,
    })


@router.post("/process")
async def process_turn(
    session_id: str = Form(...),
    text: Optional[str] = Form(default=None),
    audio: Optional[UploadFile] = File(default=None),
):
    """
    Procesa un turno de la conversación manual.
    Acepta texto transcrito o audio WAV (transcrito en memoria y descartado).
    """
    service = _get_session(session_id)
    if service is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Sesión no encontrada. Inicia una nueva llamada."},
        )

    if not service.activa:
        return JSONResponse(content={
            "result": _serialize_result(service._build_result(
                respuesta_texto="[La llamada ya no está activa]",
                intencion=service.estado.ultima_intencion(),
            )),
        })

    input_text = ""

    # Prioridad 1: audio del micrófono → transcribir en memoria y descartar bytes
    if audio is not None:
        audio_bytes = await audio.read(_MAX_AUDIO_BYTES + 1)
        if len(audio_bytes) > _MAX_AUDIO_BYTES:
            del audio_bytes
            raise HTTPException(status_code=413, detail="El audio excede el límite de 15 MB.")
        try:
            if audio_bytes and service.audio_engine.whisper_disponible:
                input_text = await service.audio_engine.transcribir_o_leer_texto(audio_bytes)
                logger.info(f"[Router] Whisper transcribió: '{input_text[:80]}'")
        finally:
            del audio_bytes

    # Prioridad 2: texto directo (modo respaldo o Web Speech API)
    if not input_text and text:
        input_text = text.strip()

    if not input_text:
        return JSONResponse(content={
            "result": _serialize_result(service._build_result(
                respuesta_texto="No se recibió entrada. Intenta hablar más fuerte o escribe tu mensaje.",
                intencion=service.estado.ultima_intencion(),
            )),
        })

    result = await service.process_call(input_text)
    response_data = await _build_turn_response(service, result, input_text)
    if not service.activa:
        _sessions.pop(session_id, None)
    return JSONResponse(content=response_data)


@router.post("/hangup")
async def hangup_call(session_id: str = Form(...)):
    """Termina la llamada manual (el usuario cuelga)."""
    service = _get_session(session_id)
    if service is None:
        return JSONResponse(status_code=404, content={"error": "Sesión no encontrada."})

    result = service.colgar()
    _sessions.pop(session_id, None)

    logger.info(f"[Router] Sesión manual terminada: {session_id}")
    return JSONResponse(content={"result": _serialize_result(result)})


# -----------------------------------------------------------------------
# Apartado B: Simulación Automática (Bot Estafador vs. Doña Lupita)
# -----------------------------------------------------------------------

@router.get("/bot/scenarios")
async def list_bot_scenarios():
    """Devuelve los escenarios E01-E08 disponibles para el bot estafador."""
    return JSONResponse(content={"scenarios": cargar_escenarios_voz()})


@router.post("/bot/start")
async def bot_start(
    scenario_id: str = Form(default="E01"),
    max_turns: int = Form(default=DEFAULT_BOT_MAX_TURNS, ge=1, le=6),
    max_duration: float = Form(default=180.0, ge=30.0, le=300.0),
    locked_avatar: AvatarId = Form(default=AvatarId.LUPITA),
    locked_voice_profile: str = Form(default=""),
):
    """Inicia una simulación controlada Bot Estafador vs. Doña Lupita."""
    bot_session_id = uuid.uuid4().hex[:12]
    engine = _get_or_create_engine()

    sim = BotEstafadorSimulator(
        scenario_id=scenario_id,
        max_turns=max_turns,
        max_duration_seconds=max_duration,
        audio_engine=engine,
        locked_avatar=locked_avatar,
        locked_voice_profile=_parse_locked_voice_profile(locked_voice_profile),
    )
    saludo = sim.iniciar()
    _bot_sessions[bot_session_id] = sim

    logger.info(f"[Router] Simulación Bot iniciada: {bot_session_id} ({scenario_id}, max_turns={sim.max_turns})")
    response_data = await _build_turn_response(sim.voice_service, saludo, "")
    response_data.update({
        "bot_session_id": bot_session_id,
        "scenario_id": sim.scenario_id,
        "description": sim.description,
        "turn_index": sim.turn_index,
        "max_turns": sim.max_turns,
        "can_advance": sim.puede_avanzar,
        "audio_status": engine.status(),
    })
    return JSONResponse(content=response_data)


@router.post("/bot/next")
async def bot_next_turn(
    bot_session_id: str = Form(...),
):
    """
    Avanza un turno del guion educativo y obtiene la respuesta de Doña Lupita.
    """
    sim = _bot_sessions.get(bot_session_id)
    if sim is None:
        return JSONResponse(status_code=404, content={"error": "Simulación no encontrada."})

    attacker_text, result = await sim.siguiente_turno()
    response_data = await _build_turn_response(sim.voice_service, result, attacker_text or "")
    response_data.update({
        "attacker_text": attacker_text,
        "turn_index": sim.turn_index,
        "max_turns": sim.max_turns,
        "can_advance": sim.puede_avanzar,
    })

    if not sim.puede_avanzar and not sim.voice_service.activa:
        _bot_sessions.pop(bot_session_id, None)

    return JSONResponse(content=response_data)


@router.post("/bot/stop")
async def bot_stop(bot_session_id: str = Form(...)):
    """Detiene manualmente la simulación automática."""
    sim = _bot_sessions.pop(bot_session_id, None)
    if sim is None:
        return JSONResponse(status_code=404, content={"error": "Simulación no encontrada."})

    result = sim.detener()
    return JSONResponse(content={
        "result": _serialize_result(result),
        "can_advance": False,
    })


# -----------------------------------------------------------------------
# Estado y archivos de audio
# -----------------------------------------------------------------------

@router.get("/status")
async def audio_status():
    """Estado del motor de audio (qué componentes están disponibles)."""
    engine = _get_or_create_engine()
    return JSONResponse(content=engine.status())


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Sirve fragmentos de audio pregrabados (.mp3 o .wav)."""
    file_path = (_ASSETS_DIR / filename).resolve()
    if (
        Path(filename).name != filename
        or file_path.parent != _ASSETS_DIR.resolve()
        or not file_path.is_file()
        or file_path.suffix not in (".wav", ".mp3")
    ):
        return JSONResponse(status_code=404, content={"error": "Audio no encontrado"})
    media_type = "audio/mpeg" if file_path.suffix == ".mp3" else "audio/wav"
    return FileResponse(str(file_path), media_type=media_type)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

async def _build_turn_response(
    service: VoiceService,
    result: CallResult,
    input_text: str,
) -> dict:
    """Construye la respuesta JSON del turno e incluye TTS dinámico si aplica."""
    tts_audio_b64 = None
    if (
        result.tts_texto
        and service.locked_voice_profile.citizen.provider == "piper"
        and service.audio_engine.piper_disponible
    ):
        wav_data = await service.audio_engine.sintetizar_dinamico(result.tts_texto)
        if wav_data:
            tts_audio_b64 = base64.b64encode(wav_data).decode("ascii")

    data = {
        "result": _serialize_result(result),
        "transcripcion_usuario": input_text,
    }
    if tts_audio_b64:
        data["tts_audio_b64"] = tts_audio_b64
    return data


def _parse_locked_voice_profile(raw_profile: str) -> Optional[LockedVoiceProfile]:
    """Valida la configuración fijada por el navegador para toda la llamada."""
    if not raw_profile:
        return None
    try:
        return LockedVoiceProfile.model_validate(json.loads(raw_profile))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(
            status_code=422,
            detail="El perfil de voz fijado no tiene un formato válido.",
        ) from exc


def _serialize_result(result: CallResult) -> dict:
    """Serializa CallResult a dict para JSON response (sin audio crudo)."""
    data = result.model_dump(mode="json")
    data.pop("evento_ref", None)
    return data
