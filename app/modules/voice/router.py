"""
router.py — Endpoints FastAPI para el módulo de voz (Doña Lupita).

Proporciona:
  - GET  /voice/           → Redirección autenticada al simulador privado
  - POST /voice/scenario/start → Iniciar escenario precargado
  - POST /voice/scenario/next  → Avanzar el siguiente parlamento del guion
  - POST /voice/hangup     → Colgar la llamada
  - GET  /voice/status     → Estado del motor de audio
  - GET  /voice/audio/{filename} → Servir fragmentos pregrabados
"""

from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse

from app.core.db import record_government_report
from app.modules.voice.audio_engine import AudioEngine
from app.modules.voice.models import CallResult
from app.modules.voice.service import VoiceService
from app.modules.citizen.sanitizer import sanitize_report
from app.modules.government.events import publish_event
from app.modules.government.auth import require_government_user
from app.modules.intel.contracts import EventInput
from app.modules.intel.service import get_default_engine
from app.modules.planting.service import attribute
from app.core.scenario_runner import list_scenarios
from app.core.schemas import Channel

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/voice",
    tags=["voice"],
    dependencies=[Depends(require_government_user)],
)

_ASSETS_DIR = Path(__file__).parent / "assets"
_MAX_AUDIO_BYTES = 15 * 1024 * 1024

# Sesiones activas en memoria
_sessions: dict[str, VoiceService] = {}
_call_metadata: dict[str, dict] = {}
_scenario_runs: dict[str, dict] = {}
_DEFAULT_DEMO_TRAP = "+52 442 000 0102"
_LONG_DIGIT_SEQUENCE = re.compile(r"(?<!\d)(?:\+?\d[\s().-]*){9,19}(?!\d)")
_DIGIT_WORD = r"cero|uno|una|un|dos|tres|cuatro|cinco|seis|siete|ocho|nueve"
_LONG_SPOKEN_DIGIT_SEQUENCE = re.compile(
    rf"(?<!\w)(?:{_DIGIT_WORD})(?:[\s,;:.-]+(?:{_DIGIT_WORD})){{7,}}(?!\w)",
    re.IGNORECASE,
)


def _sanitize_demo_text(value: str) -> str:
    """Redacta PII y enmascara secuencias numéricas antes de emitirlas al panel."""
    summary = sanitize_report(
        {"channel": "llamada", "municipality": "No especificado", "description": value}
    ).sanitized_summary

    def mask_digits(match: re.Match[str]) -> str:
        digits = re.sub(r"\D", "", match.group(0))
        masked = "•" * max(0, len(digits) - 4) + digits[-4:]
        digit_iter = iter(masked)
        return "".join(next(digit_iter) if char.isdigit() else char for char in match.group(0))

    return _LONG_DIGIT_SEQUENCE.sub(mask_digits, summary)


def _sanitize_agent_response(value: str) -> str:
    """Oculta también las CLABE pronunciadas como palabras antes de mostrarlas o sintetizarlas."""
    safe_text = _sanitize_demo_text(value)
    return _LONG_SPOKEN_DIGIT_SEQUENCE.sub("[CLABE protegida]", safe_text)


def _call_attribution(session_id: str) -> dict:
    return _call_metadata[session_id]["attribution"]


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

@router.get("/", include_in_schema=False)
async def voice_page():
    """Envía el acceso anterior del simulador a su nueva ubicación privada."""
    return RedirectResponse(url="/gobierno/simulador", status_code=307)


# -----------------------------------------------------------------------
# Apartado A: Llamada Manual
# -----------------------------------------------------------------------

@router.post("/start")
async def start_call():
    """Deshabilitado: las llamadas solo pueden iniciar desde un escenario precargado."""
    raise HTTPException(
        status_code=410,
        detail="Selecciona un escenario precargado para iniciar una llamada simulada.",
    )


async def _begin_scenario_call(scenario_id: str) -> tuple[str, dict]:
    """Abre una sesión sintética vinculada a un escenario de voz precargado."""
    if any(service.activa for service in _sessions.values()):
        publish_event(
            "call.capacity_rejected",
            {"source_mode": "simulation", "synthetic_demo": True},
        )
        raise HTTPException(
            status_code=409,
            detail="Ya hay una simulación activa. Termínala antes de iniciar otra.",
        )

    session_id = uuid.uuid4().hex[:12]
    engine = _get_or_create_engine()
    # La demo solo usa destinos sembrados y sintéticos; ignora números enviados
    # por el navegador para impedir que este flujo simulado marque números reales.
    attribution = attribute(_DEFAULT_DEMO_TRAP).model_dump()
    attribution["synthetic"] = True
    _call_metadata[session_id] = {
        "attribution": attribution,
        "caller_masked": "+52 442 XXX 8899 (ficticio)",
        "indicators": [],
        "campaign": None,
        "evidence_hash": None,
        "scenario_id": scenario_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "transcript": [],
    }

    service = VoiceService(
        max_duration_seconds=300.0,
        audio_engine=engine,
        trap_id=attribution["trap_id"],
    )
    result = service.iniciar_llamada()
    _sessions[session_id] = service
    greeting = _sanitize_agent_response(result.respuesta_texto)
    _call_metadata[session_id]["transcript"].append({
        "speaker": "victima",
        "text": greeting,
        "occurred_at": _call_metadata[session_id]["started_at"],
    })

    publish_event(
        "call.started",
        {
            "source_mode": "simulation",
            "call_id": session_id,
            "caller_masked": _call_metadata[session_id]["caller_masked"],
            "caller_id_status": "simulado_no_verificado",
            "called_number_masked": attribution.get("trap_display") or "Número trampa ficticio",
            "attribution": attribution,
            "agent": "Doña Lupita",
            "agent_response": greeting,
            "scenario_id": scenario_id,
            "synthetic_demo": True,
        },
    )

    logger.info(f"[Router] Sesión iniciada: {session_id}")

    return session_id, _serialize_result(result)


@router.post("/scenario/start")
async def start_scenario_call(scenario_id: str = Form(...)) -> dict:
    """Inicia la llamada con el guion de un escenario de voz precargado."""
    scenario = next(
        (item for item in list_scenarios() if item.id == scenario_id and item.channel == Channel.CALL),
        None,
    )
    if scenario is None:
        raise HTTPException(status_code=404, detail="No se encontró ese escenario de llamada.")
    turns = scenario.input.get("turns", [])
    if not turns or not all(isinstance(turn, str) and turn.strip() for turn in turns):
        raise HTTPException(status_code=422, detail="El escenario no contiene turnos de voz válidos.")

    session_id, greeting = await _begin_scenario_call(scenario.id)
    _scenario_runs[session_id] = {
        "scenario_id": scenario.id,
        "turns": turns,
        "next_turn": 0,
        "processing": False,
        "finished": False,
    }
    return {
        "session_id": session_id,
        "scenario_id": scenario.id,
        "greeting": greeting.get("respuesta_texto", "¡Bueno! ¿Quién habla?"),
        "turn_count": len(turns),
        "synthetic_demo": True,
    }


@router.post("/process")
async def process_turn_disabled():
    """La API ya no acepta audio ni mensajes escritos por el usuario."""
    raise HTTPException(
        status_code=410,
        detail="La conversación libre está deshabilitada. Ejecuta un escenario precargado.",
    )


async def _process_scenario_turn(session_id: str, input_text: str) -> JSONResponse:
    """Procesa una frase recuperada internamente del guion precargado."""
    run = _scenario_runs.get(session_id)
    if run is None or not run.get("processing"):
        raise HTTPException(
            status_code=410,
            detail="La conversación libre está deshabilitada. Ejecuta un escenario precargado.",
        )
    turn_index = int(run["next_turn"])
    if turn_index >= len(run["turns"]) or input_text != run["turns"][turn_index]:
        raise HTTPException(status_code=400, detail="Solo se aceptan los turnos del escenario seleccionado.")

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

    if not input_text:
        return JSONResponse(content={
            "result": _serialize_result(service._build_result(
                respuesta_texto="No se recibió entrada. Intenta hablar más fuerte o escribe tu mensaje.",
                intencion=service.estado.ultima_intencion(),
            )),
        })

    result = await service.process_call(input_text)

    sanitized_input = sanitize_report(
        {"channel": "llamada", "municipality": "No especificado", "description": input_text}
    ).sanitized_summary
    safe_transcript = _sanitize_demo_text(input_text)
    safe_agent_response = _sanitize_agent_response(result.respuesta_texto)
    occurred_at = datetime.now(timezone.utc).isoformat()
    transcript = _call_metadata[session_id].setdefault("transcript", [])
    transcript.extend((
        {"speaker": "atacante", "text": safe_transcript, "occurred_at": occurred_at},
        {"speaker": "victima", "text": safe_agent_response, "occurred_at": occurred_at},
    ))
    intel_result = get_default_engine().process_event(
        EventInput(
            event_id=result.id,
            occurred_at=occurred_at,
            channel="call",
            text_sanitized=sanitized_input,
            source_fingerprint=f"voice-sim:{session_id}",
            trap_id=service.trap_id,
            attribution_id=_call_attribution(session_id).get("copy_id"),
            origin_phone_masked=_call_metadata[session_id]["caller_masked"],
            synthetic=True,
        )
    )
    _call_metadata[session_id]["indicators"] = [
        indicator.to_dict() for indicator in intel_result.indicators
    ]
    _call_metadata[session_id]["campaign"] = {
        "campaign_id": intel_result.campaign_id,
        "status": intel_result.status,
        "confidence_level": intel_result.confidence_level,
        "confidence": intel_result.confidence,
        "threat_category": intel_result.threat_category,
    }
    _call_metadata[session_id]["evidence_hash"] = intel_result.evidence_hash
    voice_indicators = []
    for indicator in result.indicadores:
        masked_value = indicator.valor_enmascarado or indicator.enmascarar()
        voice_indicators.append(
            {
                "id": indicator.id,
                "type": indicator.tipo,
                "value_masked": masked_value,
                "valid": indicator.digito_verificador_ok,
                "status": "indicio",
                "confidence": "baja",
            }
        )
    published_indicators = [indicator.to_dict() for indicator in intel_result.indicators]
    existing_indicator_keys = {
        (item.get("type"), item.get("value_masked")) for item in published_indicators
    }
    published_indicators.extend(
        item for item in voice_indicators
        if (item["type"], item["value_masked"]) not in existing_indicator_keys
    )
    _call_metadata[session_id]["indicators"] = published_indicators

    publish_event(
        "call.turn",
        {
            "source_mode": "simulation",
            "call_id": session_id,
            "scenario_id": run["scenario_id"],
            "event_id": result.id,
            "transcript": safe_transcript,
            "intent": result.ultima_intencion.value if result.ultima_intencion else None,
            "agent_response": safe_agent_response,
            "indicators": published_indicators,
            "campaign": {
                "campaign_id": intel_result.campaign_id,
                "status": intel_result.status,
                "confidence_level": intel_result.confidence_level,
            },
            "attribution": _call_attribution(session_id),
            "evidence_hash": intel_result.evidence_hash,
            "synthetic_demo": True,
        },
    )

    if result.status.value != "active":
        metadata = _call_metadata.get(session_id, {})
        _save_call_report(session_id, result, metadata)
        publish_event(
            "call.ended",
            {
                "source_mode": "simulation",
                "call_id": session_id,
                "scenario_id": run["scenario_id"],
                "status": result.status.value,
                "duration_seconds": round(result.duracion_segundos, 1),
                "caller_masked": metadata.get("caller_masked"),
                "attribution": metadata.get("attribution"),
                "indicators": metadata.get("indicators", []),
                "campaign": metadata.get("campaign"),
                "evidence_hash": metadata.get("evidence_hash"),
                "scenario_id": metadata.get("scenario_id"),
                "synthetic_demo": True,
            },
        )
        _sessions.pop(session_id, None)

    serialized_result = _serialize_result(result)
    serialized_result["respuesta_texto"] = safe_agent_response
    response_data = {
        "result": serialized_result,
        "transcripcion_usuario": safe_transcript,
    }

    return JSONResponse(content=response_data)


@router.post("/hangup")
async def hangup_call(session_id: str = Form(...)):
    """Termina la llamada manual (el usuario cuelga)."""
    service = _get_session(session_id)
    if service is None:
        return JSONResponse(status_code=404, content={"error": "Sesión no encontrada."})

    result = service.colgar()

    metadata = _call_metadata.get(session_id, {})
    _save_call_report(session_id, result, metadata)
    scenario_run = _scenario_runs.get(session_id)
    if scenario_run is not None:
        scenario_run["finished"] = True
    publish_event(
        "call.ended",
        {
            "source_mode": "simulation",
            "call_id": session_id,
            "status": result.status.value,
            "duration_seconds": round(result.duracion_segundos, 1),
            "caller_masked": metadata.get("caller_masked"),
            "attribution": metadata.get("attribution"),
            "indicators": metadata.get("indicators", []),
            "campaign": metadata.get("campaign"),
            "evidence_hash": metadata.get("evidence_hash"),
            "scenario_id": metadata.get("scenario_id"),
            "synthetic_demo": True,
        },
    )

    # Limpiar sesión
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


@router.post("/cancel-active")
async def cancel_active_call():
    """Cierra la sesión simulada activa aunque el navegador haya perdido su ID."""
    for session_id, service in list(_sessions.items()):
        if service.activa:
            await hangup_call(session_id)
            return JSONResponse(content={"status": "cancelled", "session_id": session_id})
        _sessions.pop(session_id, None)

    return JSONResponse(content={"status": "idle"})


@router.post("/scenario/next")
async def advance_scenario_call(session_id: str = Form(...)) -> dict:
    """Procesa el siguiente parlamento precargado y cierra la llamada al terminar."""
    run = _scenario_runs.get(session_id)
    if run is None:
        raise HTTPException(status_code=404, detail="La sesión de escenario no está activa.")
    if run["finished"]:
        return {"finished": True, "scenario_id": run["scenario_id"]}
    turn_index = int(run["next_turn"])
    if turn_index >= len(run["turns"]):
        run["finished"] = True
        return {"finished": True, "scenario_id": run["scenario_id"]}

    attacker_line = run["turns"][turn_index]
    run["processing"] = True
    try:
        response = await _process_scenario_turn(session_id, attacker_line)
        run["next_turn"] = turn_index + 1
        payload = json.loads(response.body)
        call_result = payload.get("result", {})
        finished = (
            run["next_turn"] >= len(run["turns"])
            or call_result.get("status") != "active"
        )
        if finished and _get_session(session_id) is not None:
            await hangup_call(session_id=session_id)
        run["finished"] = finished
        return {
            "attacker_line": payload.get("transcripcion_usuario", _sanitize_demo_text(attacker_line)),
        "victim_line": _sanitize_agent_response(call_result.get("respuesta_texto", "")),
            "intent": call_result.get("ultima_intencion"),
            "turn": turn_index + 1,
            "turn_count": len(run["turns"]),
            "finished": finished,
            "scenario_id": run["scenario_id"],
            "synthetic_demo": True,
        }
    except Exception as exc:
        logger.exception("Falló el turno %s del escenario %s", turn_index + 1, run["scenario_id"])
        _close_failed_scenario(session_id, exc)
        raise HTTPException(
            status_code=500,
            detail="Falló un turno de la simulación. La sesión se cerró; puedes volver a intentarlo.",
        ) from exc
    finally:
        run["processing"] = False


def _close_failed_scenario(session_id: str, error: Exception) -> None:
    """Libera una sesión si un turno del escenario falla para evitar dejarla ocupada."""
    run = _scenario_runs.get(session_id)
    if run is not None:
        run["processing"] = False
        run["finished"] = True
        run["failure_type"] = type(error).__name__
    service = _sessions.pop(session_id, None)
    metadata = _call_metadata.get(session_id, {})
    if service is None:
        return
    result = service.colgar()
    metadata["failure_type"] = type(error).__name__
    try:
        _save_call_report(session_id, result, metadata)
    except Exception:
        logger.exception("No se pudo guardar el resumen de la simulación fallida %s", session_id)
    try:
        publish_event(
            "call.ended",
            {
                "source_mode": "simulation",
                "call_id": session_id,
                "scenario_id": metadata.get("scenario_id"),
                "status": result.status.value,
                "duration_seconds": round(result.duracion_segundos, 1),
                "caller_masked": metadata.get("caller_masked"),
                "attribution": metadata.get("attribution"),
                "indicators": metadata.get("indicators", []),
                "campaign": metadata.get("campaign"),
                "evidence_hash": metadata.get("evidence_hash"),
                "failure": True,
                "synthetic_demo": True,
            },
        )
    except Exception:
        logger.exception("No se pudo publicar el cierre de la simulación fallida %s", session_id)


@router.get("/status")
async def audio_status():
    """Estado del motor de audio (qué componentes están disponibles)."""
    engine = _get_or_create_engine()
    return JSONResponse(content=engine.status())


@router.get("/audio/{filename}")
async def serve_audio(filename: str):
    """Sirve fragmentos de audio pregrabados (.mp3 o .wav)."""
    if Path(filename).name != filename or filename in {".", ".."}:
        return JSONResponse(status_code=404, content={"error": "Audio no encontrado"})
    file_path = _ASSETS_DIR / filename
    if not file_path.is_file() or file_path.suffix not in (".wav", ".mp3"):
        return JSONResponse(status_code=404, content={"error": "Audio no encontrado"})
    media_type = "audio/mpeg" if file_path.suffix == ".mp3" else "audio/wav"
    return FileResponse(
        str(file_path),
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=3600"},
    )


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


def _save_call_report(session_id: str, result: CallResult, metadata: dict) -> None:
    campaign = metadata.get("campaign") or {}
    attribution = metadata.get("attribution") or {}
    indicators = metadata.get("indicators") or []
    ended_at = datetime.now(timezone.utc).isoformat()
    record_government_report(
        report_id=session_id,
        report_type="call",
        created_at=ended_at,
        channel="llamada",
        status=str(campaign.get("status") or "sin_verificar"),
        confidence=float(campaign.get("confidence") or 0),
        threat_category=campaign.get("threat_category"),
        campaign_id=campaign.get("campaign_id"),
        details={
            "call_status": result.status.value,
            "duration_seconds": round(result.duracion_segundos, 1),
            "caller_masked": metadata.get("caller_masked"),
            "copy_id": attribution.get("copy_id"),
            "source_dataset": attribution.get("source_dataset") or attribution.get("dataset"),
            "indicator_count": len(indicators),
            "evidence_hash": metadata.get("evidence_hash"),
            "draft_status": "pendiente",
            "scenario_id": metadata.get("scenario_id"),
            "session_id": session_id,
            "started_at": metadata.get("started_at"),
            "ended_at": ended_at,
            "attribution": attribution,
            "indicators": indicators,
            "campaign": campaign,
            "transcript": list(metadata.get("transcript") or []),
            "synthetic_demo": True,
            "notice": "SIMULADO — sin validez oficial. No se envió a terceros.",
        },
        synthetic=True,
    )
