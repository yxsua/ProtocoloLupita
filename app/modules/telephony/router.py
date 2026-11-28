"""Integración inicial con llamadas entrantes de Twilio y una sesión activa."""

from __future__ import annotations

import hashlib
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response
from twilio.request_validator import RequestValidator
from twilio.twiml.voice_response import VoiceResponse

from app.modules.government.events import publish_event
from app.modules.intel.contracts import EventInput
from app.modules.intel.service import IntelEngine, get_default_engine
from app.modules.planting.service import attribute
from app.modules.voice.audio_engine import AudioEngine, PiperTTS
from app.modules.voice.models import CallStatus
from app.modules.voice.service import VoiceService

router = APIRouter(prefix="/api/telephony", tags=["telephony"])
_sessions: dict[str, "PhoneSession"] = {}
_sessions_lock = threading.Lock()
_active_call_id: str | None = None
_tts_audio: dict[str, bytes] = {}
_MAX_CALL_SECONDS = 300.0
_MAX_NO_INPUT = 3
_ASSETS_DIR = Path(__file__).resolve().parents[1] / "voice" / "assets"


@dataclass
class PhoneSession:
    call_id: str
    caller_masked: str
    called_number: str
    trap_id: str
    attribution: dict[str, Any]
    service: VoiceService
    intel: IntelEngine
    opened_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    no_input_count: int = 0
    latest_indicators: list[dict[str, Any]] = field(default_factory=list)
    latest_campaign: dict[str, Any] | None = None
    latest_evidence_hash: str | None = None
    ended: bool = False


@lru_cache(maxsize=1)
def _validator() -> RequestValidator:
    token = os.getenv("TWILIO_AUTH_TOKEN", "")
    if not token:
        raise RuntimeError("TWILIO_AUTH_TOKEN no está configurado")
    return RequestValidator(token)


def _public_url(path: str, query: dict[str, str] | None = None) -> str:
    url = f"{os.getenv('PUBLIC_BASE_URL', '').rstrip('/')}{path}"
    return f"{url}?{urlencode(query)}" if query else url


async def _validate_twilio(request: Request, form: Any) -> bool:
    signature = request.headers.get("X-Twilio-Signature", "")
    if not signature:
        return False
    try:
        url = _public_url(request.url.path, dict(request.query_params))
        return bool(_validator().validate(url, form, signature))
    except RuntimeError:
        return False


def _mask_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value)
    return f"••• ••• {digits[-4:]}" if len(digits) >= 4 else "No disponible"


def _mask_transcript(value: str) -> str:
    def mask(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        masked = "•" * max(0, len(digits) - 4) + digits[-4:]
        iterator = iter(masked)
        return "".join(next(iterator) if char.isdigit() else char for char in match.group(0))

    return re.sub(r"(?<!\d)(?:\+?\d[\s-]*){9,19}(?!\d)", mask, value)


def _build_audio_engine() -> AudioEngine:
    tts = PiperTTS(model_path=os.getenv("PIPER_MODEL_PATH") or None, length_scale=1.08)
    return AudioEngine(tts=tts, assets_dir=str(_ASSETS_DIR))


def _twiml_response(response: VoiceResponse) -> Response:
    return Response(content=str(response), media_type="application/xml")


def _add_gather(response: VoiceResponse, call_id: str) -> None:
    gather = response.gather(
        input="speech",
        language=os.getenv("TWILIO_GATHER_LANGUAGE", "es-MX"),
        speech_model=os.getenv("TWILIO_SPEECH_MODEL", "deepgram_nova-3"),
        speech_timeout="auto",
        timeout=5,
        action_on_empty_result=True,
        action=_public_url("/api/telephony/turn"),
        method="POST",
        partial_result_callback=_public_url("/api/telephony/partial"),
        partial_result_callback_method="POST",
        profanity_filter=False,
    )
    gather.play(_public_url("/voice/audio/espera_pensando_01.wav"))


def _play_response(response: VoiceResponse, audio_ref: str | None, fallback_text: str) -> None:
    if audio_ref:
        candidate = Path(audio_ref).name
        if (
            candidate == audio_ref
            and Path(candidate).suffix.lower() in {".wav", ".mp3"}
            and (_ASSETS_DIR / candidate).is_file()
        ):
            response.play(_public_url(f"/voice/audio/{candidate}"))
            return
    response.say(fallback_text[:450], language="es-MX")


def _finish_session(session: PhoneSession, reason: str) -> None:
    global _active_call_id
    with _sessions_lock:
        if session.ended:
            return
        session.ended = True
        _sessions.pop(session.call_id, None)
        if _active_call_id == session.call_id:
            _active_call_id = None
        _tts_audio.clear()
    publish_event(
        "call.ended",
        {
            "source_mode": "telephony",
            "call_id": session.call_id,
            "status": reason,
            "duration_seconds": round(session.service.duracion_actual, 1),
            "caller_masked": session.caller_masked,
            "attribution": session.attribution,
            "indicators": session.latest_indicators,
            "campaign": session.latest_campaign,
            "evidence_hash": session.latest_evidence_hash,
            "synthetic_demo": True,
        },
    )


@router.post("/voice")
async def incoming_call(request: Request) -> Response:
    global _active_call_id
    form = await request.form()
    if not await _validate_twilio(request, form):
        return JSONResponse(status_code=403, content={"error": "Firma de proveedor no válida."})

    base_url = os.getenv("PUBLIC_BASE_URL", "")
    test_number = os.getenv("TWILIO_TEST_NUMBER", "")
    trap_id = os.getenv("TWILIO_TEST_TRAP_ID", "")
    if not (base_url.startswith("https://") and test_number and trap_id):
        return JSONResponse(status_code=503, content={"error": "Falta configurar el servidor y número de prueba."})

    call_id = str(form.get("CallSid", ""))
    caller = str(form.get("From", ""))
    called = str(form.get("To", ""))
    if not call_id or re.sub(r"\D", "", called) != re.sub(r"\D", "", test_number):
        response = VoiceResponse()
        response.say("Este número de prueba no está habilitado.", language="es-MX")
        response.hangup()
        return _twiml_response(response)

    with _sessions_lock:
        if _active_call_id and _active_call_id != call_id:
            response = VoiceResponse()
            response.say(
                "En este momento la línea de demostración está ocupada. Intente de nuevo en un momento.",
                language="es-MX",
            )
            response.hangup()
            publish_event("call.capacity_rejected", {"source_mode": "telephony", "call_id": call_id})
            return _twiml_response(response)
        session = _sessions.get(call_id)
        is_new_session = session is None
        if session is None:
            attribution_result = attribute(trap_id)
            attribution = {
                "status": attribution_result.status,
                "trap_id": attribution_result.trap_id,
                "copy_id": attribution_result.copy_id,
                "source_dataset": attribution_result.source_dataset,
                "provider": attribution_result.provider,
                "seed_period": attribution_result.seed_period,
                "synthetic": attribution_result.synthetic,
            }
            session = PhoneSession(
                call_id=call_id,
                caller_masked=_mask_phone(caller),
                called_number=_mask_phone(called),
                trap_id=trap_id,
                attribution=attribution,
                service=VoiceService(
                    max_duration_seconds=_MAX_CALL_SECONDS,
                    audio_engine=_build_audio_engine(),
                    trap_id=trap_id,
                ),
                intel=get_default_engine(),
            )
            _sessions[call_id] = session
            _active_call_id = call_id

    response = VoiceResponse()
    if is_new_session:
        greeting = session.service.iniciar_llamada()
        publish_event(
            "call.started",
            {
                "source_mode": "telephony",
                "call_id": call_id,
                "caller_masked": session.caller_masked,
                "caller_id_status": "no_verificado",
                "called_number_masked": session.called_number,
                "attribution": session.attribution,
                "agent": "Doña Lupita",
                "synthetic_demo": True,
            },
        )
        _play_response(response, greeting.audio_ref, greeting.respuesta_texto)
    _add_gather(response, call_id)
    response.redirect(_public_url("/api/telephony/timeout", {"CallSid": call_id}), method="POST")
    return _twiml_response(response)


@router.post("/turn")
async def process_phone_turn(request: Request) -> Response:
    form = await request.form()
    if not await _validate_twilio(request, form):
        return JSONResponse(status_code=403, content={"error": "Firma de proveedor no válida."})
    call_id = str(form.get("CallSid", ""))
    session = _sessions.get(call_id)
    response = VoiceResponse()
    if session is None:
        response.say("La sesión terminó. Gracias.", language="es-MX")
        response.hangup()
        return _twiml_response(response)

    text = str(form.get("SpeechResult", "")).strip()
    session.no_input_count = session.no_input_count + 1 if not text else 0
    if session.service.duracion_actual >= _MAX_CALL_SECONDS or session.no_input_count >= _MAX_NO_INPUT:
        response.say("Muchas gracias, joven. Que tenga buen día.", language="es-MX")
        response.hangup()
        _finish_session(session, "timeout" if text else "sin_entrada")
        return _twiml_response(response)

    if not text:
        response.play(_public_url("/voice/audio/pedir_repeticion_01.wav"))
        _add_gather(response, call_id)
        response.redirect(_public_url("/api/telephony/timeout", {"CallSid": call_id}), method="POST")
        return _twiml_response(response)

    confidence_raw = str(form.get("Confidence", ""))
    try:
        speech_confidence = round(float(confidence_raw), 2) if confidence_raw else None
    except ValueError:
        speech_confidence = None

    result = await session.service.process_call(text)
    turn_number = sum(1 for turn in session.service.estado.turnos if turn.rol == "usuario")
    event_id = f"{call_id}-{turn_number}"
    source_fingerprint = hashlib.sha256(call_id.encode("utf-8")).hexdigest()
    intel_result = session.intel.process_event(EventInput(
        event_id=event_id,
        occurred_at=datetime.now(timezone.utc).isoformat(),
        channel="call",
        text_sanitized=text,
        source_fingerprint=source_fingerprint,
        trap_id=session.trap_id,
        attribution_id=session.attribution.get("copy_id"),
        origin_phone_masked=session.caller_masked,
        synthetic=True,
    ))
    indicators = [indicator.to_dict() for indicator in intel_result.indicators]
    campaign = {
        "campaign_id": intel_result.campaign_id,
        "status": intel_result.status,
        "confidence_level": intel_result.confidence_level,
        "threat_category": intel_result.threat_category,
    }
    session.latest_indicators = indicators
    session.latest_campaign = campaign
    session.latest_evidence_hash = intel_result.evidence_hash
    publish_event(
        "call.turn",
        {
            "source_mode": "telephony",
            "call_id": call_id,
            "event_id": event_id,
            "turn": turn_number,
            "transcript": _mask_transcript(text),
            "transcript_status": "enmascarado_para_la_demo",
            "speech_confidence": speech_confidence,
            "agent_response": _mask_transcript(result.respuesta_texto),
            "intent": result.ultima_intencion.value if result.ultima_intencion else None,
            "indicators": indicators,
            "campaign": campaign,
            "attribution": session.attribution,
            "evidence_hash": intel_result.evidence_hash,
            "synthetic_demo": True,
        },
    )

    if result.tts_texto:
        audio_data = await session.service.audio_engine.sintetizar_dinamico(result.tts_texto)
        if audio_data:
            token = uuid.uuid4().hex
            _tts_audio[token] = audio_data
            response.play(_public_url(f"/api/telephony/audio/{token}"))
        else:
            response.say(result.tts_texto[:450], language="es-MX")
    else:
        _play_response(response, result.audio_ref, result.respuesta_texto)

    if result.status != CallStatus.ACTIVE or session.service.duracion_actual >= _MAX_CALL_SECONDS:
        response.hangup()
        _finish_session(session, result.status.value)
        return _twiml_response(response)

    _add_gather(response, call_id)
    response.redirect(_public_url("/api/telephony/timeout", {"CallSid": call_id}), method="POST")
    return _twiml_response(response)


@router.post("/partial")
async def partial_phone_transcript(request: Request) -> Response:
    form = await request.form()
    if not await _validate_twilio(request, form):
        return JSONResponse(status_code=403, content={"error": "Firma de proveedor no válida."})
    call_id = str(form.get("CallSid", ""))
    partial = _mask_transcript(str(form.get("UnstableSpeechResult", "")).strip())
    if call_id in _sessions and partial:
        publish_event(
            "call.partial",
            {"source_mode": "telephony", "call_id": call_id, "transcript": partial, "provisional": True},
        )
    return Response(status_code=204)


@router.post("/timeout")
async def no_input_timeout(request: Request) -> Response:
    form = await request.form()
    if not await _validate_twilio(request, form):
        return JSONResponse(status_code=403, content={"error": "Firma de proveedor no válida."})
    session = _sessions.get(str(form.get("CallSid", "")))
    response = VoiceResponse()
    if session is None:
        response.hangup()
        return _twiml_response(response)
    session.no_input_count += 1
    if session.no_input_count >= _MAX_NO_INPUT or session.service.duracion_actual >= _MAX_CALL_SECONDS:
        response.say("Muchas gracias, joven. Que tenga buen día.", language="es-MX")
        response.hangup()
        _finish_session(session, "timeout")
    else:
        response.play(_public_url("/voice/audio/pedir_repeticion_01.wav"))
        _add_gather(response, session.call_id)
        response.redirect(_public_url("/api/telephony/timeout", {"CallSid": session.call_id}), method="POST")
    return _twiml_response(response)


@router.post("/status")
async def call_status(request: Request) -> Response:
    form = await request.form()
    if not await _validate_twilio(request, form):
        return JSONResponse(status_code=403, content={"error": "Firma de proveedor no válida."})
    if str(form.get("CallStatus", "")) == "completed":
        session = _sessions.get(str(form.get("CallSid", "")))
        if session:
            _finish_session(session, "completed")
    return Response(status_code=204)


@router.get("/audio/{token}")
async def synthesized_audio(token: str) -> Response:
    audio_data = _tts_audio.get(token)
    if audio_data is None:
        return Response(status_code=404)
    return Response(
        content=audio_data,
        media_type="audio/wav",
        headers={"Cache-Control": "no-store"},
    )
