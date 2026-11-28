"""
router.py — Endpoints FastAPI para el módulo de voz (Doña Lupita).

Proporciona:
  - GET  /voice/           → Página de la interfaz de llamada
  - POST /voice/start      → Iniciar sesión de llamada
  - POST /voice/process    → Procesar turno (texto o audio)
  - POST /voice/hangup     → Colgar la llamada
  - GET  /voice/status     → Estado del motor de audio
  - GET  /voice/audio/{filename} → Servir fragmentos pregrabados
"""

from __future__ import annotations

import base64
import logging
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from app.modules.voice.audio_engine import AudioEngine, TextInputAdapter, WebAudioCapture
from app.modules.voice.models import CallResult, CallStatus
from app.modules.voice.service import VoiceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voice", tags=["voice"])

# Templates
_TEMPLATES_DIR = Path(__file__).resolve().parents[2] / "templates" / "voice"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Assets
_ASSETS_DIR = Path(__file__).parent / "assets"

# Sesiones activas (en memoria, por ID de sesión)
_sessions: dict[str, VoiceService] = {}


def _get_or_create_engine() -> AudioEngine:
    """Crea el AudioEngine para el contexto web."""
    return AudioEngine.for_web(assets_dir=str(_ASSETS_DIR))


def _get_session(session_id: str) -> Optional[VoiceService]:
    return _sessions.get(session_id)


# -----------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def voice_page(request: Request):
    """Página principal de la interfaz de llamada."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": "Doña Lupita — Simulador de Llamada"},
    )


@router.post("/start")
async def start_call(
    max_duration: float = Form(default=300.0),
    trap_id: Optional[str] = Form(default=None),
):
    """Inicia una nueva sesión de llamada."""
    session_id = uuid.uuid4().hex[:12]
    engine = _get_or_create_engine()

    service = VoiceService(
        max_duration_seconds=max_duration,
        audio_engine=engine,
        trap_id=trap_id,
    )
    result = service.iniciar_llamada()
    _sessions[session_id] = service

    logger.info(f"[Router] Sesión iniciada: {session_id}")

    return JSONResponse(content={
        "session_id": session_id,
        "result": _serialize_result(result),
        "audio_status": engine.status(),
    })


@router.post("/process")
async def process_turn(
    session_id: str = Form(...),
    text: Optional[str] = Form(default=None),
    audio: Optional[UploadFile] = File(default=None),
):
    """
    Procesa un turno de la conversación.

    Acepta texto directo O audio WAV del micrófono del navegador.
    Si viene audio y Whisper está disponible, transcribe primero.
    Si no, usa el texto proporcionado (modo respaldo).
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

    # Prioridad 1: audio del micrófono → transcribir con Whisper
    if audio is not None:
        audio_bytes = await audio.read()
        if audio_bytes and service.audio_engine.whisper_disponible:
            # Alimentar el audio al adaptador web
            if isinstance(service.audio_engine.capture, WebAudioCapture):
                service.audio_engine.capture.feed_audio(audio_bytes)
            # Transcribir
            input_text = await service.audio_engine.transcribir_o_leer_texto(audio_bytes)
            logger.info(f"[Router] Whisper transcribió: '{input_text[:80]}'")

    # Prioridad 2: texto directo (modo respaldo)
    if not input_text and text:
        input_text = text.strip()

    if not input_text:
        return JSONResponse(content={
            "result": _serialize_result(service._build_result(
                respuesta_texto="No se recibió entrada. Intenta hablar más fuerte o escribe tu mensaje.",
                intencion=service.estado.ultima_intencion(),
            )),
        })

    # Procesar el turno
    result = await service.process_call(input_text)

    # Si hay TTS dinámico y Piper está disponible, sintetizar
    tts_audio_b64 = None
    if result.tts_texto and service.audio_engine.piper_disponible:
        wav_data = await service.audio_engine.sintetizar_dinamico(result.tts_texto)
        if wav_data:
            tts_audio_b64 = base64.b64encode(wav_data).decode("ascii")

    response_data = {
        "result": _serialize_result(result),
        "transcripcion_usuario": input_text,
    }

    if tts_audio_b64:
        response_data["tts_audio_b64"] = tts_audio_b64

    return JSONResponse(content=response_data)


@router.post("/hangup")
async def hangup_call(session_id: str = Form(...)):
    """Termina la llamada (el usuario cuelga)."""
    service = _get_session(session_id)
    if service is None:
        return JSONResponse(
            status_code=404,
            content={"error": "Sesión no encontrada."},
        )

    result = service.colgar()

    # Limpiar sesión
    _sessions.pop(session_id, None)

    logger.info(f"[Router] Sesión terminada: {session_id}")
    return JSONResponse(content={
        "result": _serialize_result(result),
    })


@router.get("/status")
async def audio_status():
    """Estado del motor de audio (qué componentes están disponibles)."""
    engine = _get_or_create_engine()
    return JSONResponse(content=engine.status())


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Sirve fragmentos de audio pregrabados (.mp3 o .wav)."""
    file_path = _ASSETS_DIR / filename
    if not file_path.exists() or file_path.suffix not in (".wav", ".mp3"):
        return JSONResponse(status_code=404, content={"error": "Audio no encontrado"})
    media_type = "audio/mpeg" if file_path.suffix == ".mp3" else "audio/wav"
    return FileResponse(str(file_path), media_type=media_type)


# -----------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------

def _serialize_result(result: CallResult) -> dict:
    """Serializa CallResult a dict para JSON response."""
    data = result.model_dump(mode="json")
    # Eliminar campos internos innecesarios para el frontend
    data.pop("evento_ref", None)
    return data
