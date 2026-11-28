"""
service.py — Servicio principal del módulo de voz (Doña Lupita).

Función principal: process_call(input) -> CallResult
Orquesta el flujo completo: recibe texto/audio, selecciona intención,
genera respuesta, extrae indicadores y controla duración.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.modules.voice.audio_engine import AudioEngine, TextInputAdapter
from app.modules.voice.clabe_extractor import (
    extraer_clabe,
    formatear_digitos_para_voz,
    palabras_a_digitos,
    validar_digito_verificador_clabe,
)
from app.modules.voice.models import (
    AvatarId,
    CallResult,
    CallStatus,
    EstadoConversacion,
    IndicadorCandidato,
    Intencion,
    LockedVoiceProfile,
    NivelConfianza,
    SpeakerVoiceProfile,
)
from app.modules.voice.policy import (
    detectar_prompt_injection,
    generar_respuesta,
    respuesta_anti_injection,
    seleccionar_intencion,
    seleccionar_intencion_local,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuración por defecto
# ---------------------------------------------------------------------------

DEFAULT_MAX_DURATION_SECONDS: float = 300.0  # 5 minutos
DEFAULT_OLLAMA_ENABLED: bool = False
DEFAULT_OLLAMA_TIMEOUT_MS: int = 2000

AVATAR_NAMES = {
    AvatarId.LUPITA: "Doña Lupita",
    AvatarId.RAMIRO: "Don Ramiro",
    AvatarId.CARMEN: "Sra. Carmen",
    AvatarId.HECTOR: "Profe Héctor",
}

_APERTURAS_INICIALES = {
    AvatarId.LUPITA: (
        "¿Bueno? Soy Lupita; estaba en la cocina y apenas alcancé a llegar al teléfono. ¿Quién me llama?",
        "Bueno, habla Doña Lupita. Disculpe, ¿es del banco o es alguien conocido?",
        "¿Sí? Soy Lupita. No reconozco este número, ¿con quién tengo el gusto?",
        "Bueno, ya contesté. Soy Lupita; estaba en la sala, dígame, ¿quién habla?",
        "¿Bueno? Aquí Lupita. ¿Me llama alguien de la familia o del banco?",
        "Sí, soy Lupita. Espéreme tantito... ya estoy aquí, ¿quién me busca?",
        "¿Quién habla? Soy Lupita; no escuché bien desde la cocina.",
        "¿Diga? Soy Doña Lupita. ¿Me habla el banco o se equivocó de número?",
        "Buenas, soy Lupita. ¿Me puede decir su nombre antes de contarme?",
        "Bueno, soy Lupita. Estaba acomodando mis cosas, ¿qué se le ofrece?",
        "¿Aló? Habla Lupita. Dígame despacito quién llama, por favor.",
        "¿Sí? Soy Lupita; pensé que era alguien de mi familia. ¿Quién me habla?",
    ),
    AvatarId.RAMIRO: (
        "¿Bueno? Soy Ramiro, estaba en el patio. ¿Quién habla?",
        "Bueno, habla Don Ramiro. ¿Me dice quién llama?",
        "Casi no oigo; soy Ramiro. ¿Es alguien que conozco?",
        "Sí, soy Ramiro, estaba leyendo. Dígame, ¿quién me busca?",
        "¿Bueno? Don Ramiro al teléfono, ¿de parte de quién?",
        "Hola, habla Ramiro. ¿Es una llamada de servicio o de alguien conocido?",
    ),
    AvatarId.CARMEN: (
        "¿Bueno? Soy Carmen, estaba en la cocina. ¿Quién habla?",
        "Buenas tardes, soy la señora Carmen; ¿me dice quién llama?",
        "¿Sí? Habla Carmen. Este número no lo tengo guardado, ¿quién me busca?",
        "Bueno, Carmen al habla; dígame, ¿con quién tengo el gusto?",
        "¿Diga? Soy Carmen, estaba en la sala. ¿Me llama alguien conocido?",
        "Hola, soy Carmen; ¿es una llamada de servicio o de alguien de mi familia?",
    ),
    AvatarId.HECTOR: (
        "¿Bueno? Soy Héctor, estaba preparando mis cosas. ¿Quién me llama?",
        "Hola, habla Héctor. ¿Me dice su nombre, por favor?",
        "¿Sí? Soy el Profe Héctor, aunque no reconozco este número. ¿De parte de quién?",
        "Buenas, Héctor al teléfono. Dígame, ¿qué se le ofrece?",
        "¿Aló? Soy Héctor; estaba ocupado y no escuché bien. ¿Quién habla?",
        "Hola, soy Héctor. ¿Me llama alguien conocido o es una llamada de servicio?",
    ),
}

_AVATAR_VOICE_DEFAULTS = {
    AvatarId.LUPITA: ("female", 0.88, 1.0),
    AvatarId.RAMIRO: ("male", 0.92, 0.9),
    AvatarId.CARMEN: ("female", 0.88, 1.02),
    AvatarId.HECTOR: ("male", 0.96, 0.94),
}
_ULTIMA_APERTURA_INICIAL: Optional[str] = None
_APERTURA_LOCK = threading.Lock()


def _siguiente_apertura_inicial(avatar_id: AvatarId) -> str:
    global _ULTIMA_APERTURA_INICIAL
    with _APERTURA_LOCK:
        opciones = [
            apertura
            for apertura in _APERTURAS_INICIALES[avatar_id]
            if apertura != _ULTIMA_APERTURA_INICIAL
        ]
        if not opciones:
            opciones = list(_APERTURAS_INICIALES[avatar_id])
        apertura = secrets.choice(opciones)
        _ULTIMA_APERTURA_INICIAL = apertura
        return apertura


def _default_voice_profile(avatar_id: AvatarId) -> LockedVoiceProfile:
    _, rate, pitch = _AVATAR_VOICE_DEFAULTS[avatar_id]
    return LockedVoiceProfile(
        citizen=SpeakerVoiceProfile(rate=rate, pitch=pitch),
        attacker=SpeakerVoiceProfile(rate=1.08, pitch=0.88),
    )


# ---------------------------------------------------------------------------
# Servicio de llamada
# ---------------------------------------------------------------------------

class VoiceService:
    """
    Servicio que gestiona una sesión de llamada/conversación con Doña Lupita.

    Mantiene el estado de la conversación y procesa cada turno del usuario.
    Funciona tanto en modo audio como en modo texto de respaldo.
    """

    def __init__(
        self,
        max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
        usar_ollama: bool = DEFAULT_OLLAMA_ENABLED,
        ollama_timeout_ms: int = DEFAULT_OLLAMA_TIMEOUT_MS,
        audio_engine: Optional[AudioEngine] = None,
        trap_id: Optional[str] = None,
        locked_avatar: AvatarId | str = AvatarId.LUPITA,
        locked_voice_profile: Optional[LockedVoiceProfile] = None,
    ) -> None:
        self.max_duration_seconds = max_duration_seconds
        self.usar_ollama = usar_ollama
        self.ollama_timeout_ms = ollama_timeout_ms
        self.audio_engine = audio_engine or AudioEngine()
        self.trap_id = trap_id
        self._locked_avatar = AvatarId(locked_avatar)
        self._locked_voice_profile = locked_voice_profile or _default_voice_profile(
            self._locked_avatar
        )

        # Estado mutable de la sesión
        self.estado = EstadoConversacion(
            locked_avatar=self._locked_avatar,
            locked_voice_profile=self._locked_voice_profile.model_copy(deep=True),
        )
        self._start_time: Optional[float] = None
        self._turno_counter: int = 0

    # -------------------------------------------------------------------
    # Propiedades
    # -------------------------------------------------------------------

    @property
    def duracion_actual(self) -> float:
        """Duración en segundos desde el inicio de la llamada."""
        if self._start_time is None:
            return 0.0
        return time.monotonic() - self._start_time

    @property
    def tiempo_restante(self) -> float:
        """Segundos restantes antes del corte automático."""
        return max(0.0, self.max_duration_seconds - self.duracion_actual)

    @property
    def activa(self) -> bool:
        """True si la llamada sigue activa."""
        return self.estado.status == CallStatus.ACTIVE

    @property
    def locked_avatar(self) -> AvatarId:
        return self._locked_avatar

    @property
    def locked_voice_profile(self) -> LockedVoiceProfile:
        return self._locked_voice_profile

    # -------------------------------------------------------------------
    # Inicio y fin de llamada
    # -------------------------------------------------------------------

    def iniciar_llamada(self) -> CallResult:
        """Inicia la sesión de llamada. Devuelve el saludo inicial de Lupita."""
        self._start_time = time.monotonic()
        self.estado = EstadoConversacion(
            locked_avatar=self.locked_avatar,
            locked_voice_profile=self.locked_voice_profile.model_copy(deep=True),
        )
        self.estado.status = CallStatus.ACTIVE
        self._turno_counter = 0

        saludo = _siguiente_apertura_inicial(self.locked_avatar)
        self.estado.agregar_turno("lupita", saludo, Intencion.ASUSTARSE)

        return self._build_result(
            respuesta_texto=saludo,
            tts_texto=saludo,
            intencion=Intencion.ASUSTARSE,
        )

    def colgar(self) -> CallResult:
        """El usuario cuelga la llamada."""
        self.estado.status = CallStatus.USER_HANGUP
        return self._build_result(
            respuesta_texto="[Llamada terminada por el usuario]",
            intencion=self.estado.ultima_intencion(),
        )

    def _verificar_timeout(self) -> bool:
        """Verifica si se alcanzó el límite de duración."""
        if self.duracion_actual >= self.max_duration_seconds:
            self.estado.status = CallStatus.TIMEOUT
            return True
        return False

    # -------------------------------------------------------------------
    # Función principal: process_call
    # -------------------------------------------------------------------

    async def process_call(self, input_text: str) -> CallResult:
        """
        Procesa un turno de la conversación.

        Contrato de integración:
            Recibe texto del usuario (transcripción o entrada directa).
            Devuelve CallResult con transcripción, intención, indicadores,
            duración, estado y respuesta — sin audio crudo.

        Args:
            input_text: Texto del usuario (transcripción de Whisper o entrada manual).

        Returns:
            CallResult con toda la información del turno procesado.
        """
        # Iniciar temporizador si no está activo
        if self._start_time is None:
            self._start_time = time.monotonic()

        # Verificar timeout
        if self._verificar_timeout():
            return self._build_result(
                respuesta_texto="[Llamada terminada automáticamente por límite de tiempo]",
                intencion=self.estado.ultima_intencion(),
            )

        # Verificar si ya no está activa
        if not self.activa:
            return self._build_result(
                respuesta_texto="[La llamada ya no está activa]",
                intencion=self.estado.ultima_intencion(),
            )

        self._turno_counter += 1
        fuente = f"dictado_{self._turno_counter}"

        # Registrar turno del usuario
        self.estado.agregar_turno("usuario", input_text)

        # 1. Guardrail: detectar prompt injection
        if detectar_prompt_injection(input_text):
            logger.warning(f"⚠️  Prompt injection detectado: {input_text[:50]}...")
            respuesta = respuesta_anti_injection(AVATAR_NAMES[self.locked_avatar])
            self.estado.agregar_turno("lupita", respuesta, Intencion.DAR_LARGAS)
            return self._build_result(
                respuesta_texto=respuesta,
                audio_ref="dar_largas_01.wav",
                intencion=Intencion.DAR_LARGAS,
            )

        # 2. Intentar extraer CLABE del texto
        indicador_clabe = self._procesar_clabe(input_text, fuente)

        # 3. Seleccionar intención
        intencion = await seleccionar_intencion(
            input_text,
            self.estado,
            usar_ollama=self.usar_ollama,
            ollama_timeout_ms=self.ollama_timeout_ms,
        )

        # 4. Si hay CLABE con dígito verificador incorrecto → pedir repetición
        if indicador_clabe and indicador_clabe.digito_verificador_ok is False:
            intencion = Intencion.PEDIR_REPETICION
            self.estado.confirmaciones_pendientes += 1

        # 5. Generar respuesta en personaje
        digitos_para_repetir = None
        if intencion == Intencion.REPETIR_DIGITOS and indicador_clabe:
            digitos_para_repetir = indicador_clabe.valor

        texto_resp, audio_ref, tts_texto = generar_respuesta(
            intencion, self.estado, digitos_para_repetir
        )

        # 6. Registrar turno de Lupita
        self.estado.agregar_turno("lupita", texto_resp, intencion)

        # 7. Si la intención es despedirse, completar la llamada
        if intencion == Intencion.DESPEDIRSE:
            self.estado.status = CallStatus.COMPLETED

        # 8. Verificar timeout de nuevo (el procesamiento tomó tiempo)
        self._verificar_timeout()

        return self._build_result(
            respuesta_texto=texto_resp,
            audio_ref=audio_ref,
            tts_texto=tts_texto,
            intencion=intencion,
        )

    # -------------------------------------------------------------------
    # Extracción de CLABE
    # -------------------------------------------------------------------

    def _procesar_clabe(
        self, texto: str, fuente: str
    ) -> Optional[IndicadorCandidato]:
        """Intenta extraer una CLABE del texto y actualiza indicadores."""
        # Buscar si ya hay un indicador CLABE previo
        previo = None
        for ind in self.estado.indicadores:
            if ind.tipo == "clabe":
                previo = ind
                break

        indicador = extraer_clabe(texto, fuente=fuente, indicador_previo=previo)

        if indicador is not None:
            # Si es nuevo (no es el previo actualizado), agregarlo
            if previo is None or previo.id != indicador.id:
                self.estado.indicadores.append(indicador)

            # Marcar como fuente única si aplica
            if indicador.es_fuente_unica():
                indicador.confianza = NivelConfianza.BAJA

        return indicador

    # -------------------------------------------------------------------
    # Construcción de resultado
    # -------------------------------------------------------------------

    def _build_result(
        self,
        respuesta_texto: str,
        intencion: Optional[Intencion] = None,
        audio_ref: Optional[str] = None,
        tts_texto: Optional[str] = None,
    ) -> CallResult:
        """Construye el CallResult para devolver al llamador."""
        # Transcripción consolidada
        transcripcion = "\n".join(
            f"{'Atacante' if t.rol == 'usuario' else 'Lupita'}: {t.texto}"
            for t in self.estado.turnos
        )

        self.estado.duracion_segundos = self.duracion_actual

        return CallResult(
            transcripcion_completa=transcripcion,
            ultima_intencion=intencion,
            indicadores=list(self.estado.indicadores),
            duracion_segundos=self.duracion_actual,
            status=self.estado.status,
            trap_id=self.trap_id,
            respuesta_texto=respuesta_texto,
            audio_ref=audio_ref,
            tts_texto=tts_texto,
            locked_avatar=self.locked_avatar,
            locked_voice_profile=self.locked_voice_profile.model_copy(deep=True),
            timestamp_fin=datetime.utcnow() if self.estado.status != CallStatus.ACTIVE else None,
        )


# ---------------------------------------------------------------------------
# Función de conveniencia (punto de entrada simple)
# ---------------------------------------------------------------------------

async def process_call(input_text: str, service: Optional[VoiceService] = None) -> CallResult:
    """
    Punto de entrada compatible con el contrato de integración.

    process_call(input) -> CallResult

    Si no se proporciona un servicio, crea uno nuevo (una llamada por invocación).
    Para conversaciones con estado, reutilizar la misma instancia de VoiceService.
    """
    if service is None:
        service = VoiceService()
        service.iniciar_llamada()
    return await service.process_call(input_text)


# ---------------------------------------------------------------------------
# Simulador de Bot Estafador (Human-in-the-Loop con límite de turnos)
# ---------------------------------------------------------------------------

DEFAULT_BOT_MAX_TURNS: int = 6
MAX_BOT_TURNS_LIMIT: int = 6

_GUIONES_SIMULACION_EDUCATIVA: dict[str, list[str]] = {
    "E01": [
        "Buenas tardes, soy del área de seguridad. Le llamo por un cargo que quizá usted no reconoce.",
        "Yo puedo ayudarle, pero le recomiendo que revise sus movimientos desde la aplicación oficial.",
        "Entiendo que quiera verificar quién soy; no puedo demostrarlo solo por esta llamada.",
        "Si prefiere, puede colgar y llamar al número publicado por su banco.",
        "Yo no le pediré contraseñas, códigos ni que mueva dinero durante esta llamada.",
        "Puede reportar el cargo directamente con su institución cuando usted lo decida.",
    ],
    "E02": [
        "Soy del área de tarjetas; le llamo por un supuesto aviso de bloqueo de su tarjeta o pensión.",
        "Quiero que lo resolvamos ahora, pero usted puede verificar el aviso por otro canal.",
        "Comprendo que dude; no puedo probar mi identidad solo porque conozca su número.",
        "Si recibe una alerta, consulte su aplicación o llame al número que aparece en su tarjeta.",
        "No comparta conmigo contraseñas, códigos ni números completos de tarjeta.",
        "Usted puede terminar esta llamada y confirmar el aviso directamente con su institución.",
    ],
    "E03": [
        "Le llamo por una supuesta cuenta de resguardo, pero no transfiera dinero por indicación telefónica.",
        "Para esta práctica, la CLABE 000000000000000001 es ficticia, inválida y no debe utilizarse.",
        "Una llamada inesperada no puede demostrar que una cuenta sea segura.",
        "Usted puede colgar y verificar cualquier aviso con su institución por un canal oficial.",
        "Yo no necesito que comparta sus datos bancarios para esta demostración.",
        "No realice transferencias a cuentas que alguien le indique por teléfono.",
    ],
    "E04": [
        "Le llamo porque aparece un supuesto bono o apoyo pendiente a su nombre.",
        "Yo le diré que hay prisa, pero usted no necesita decidir bajo presión.",
        "Desconfíe si alguien le promete un apoyo a cambio de información sensible o un pago.",
        "Puede revisar convocatorias directamente en el sitio oficial de la institución.",
        "Yo no puedo garantizar un depósito ni pedirle una cuota para liberar un apoyo.",
        "Si no esperaba esta llamada, cuelgue y consulte por su cuenta.",
    ],
    "E05": [
        "Soy de soporte técnico y le llamo por un supuesto problema en su equipo.",
        "Quiero que actúe rápido, aunque usted puede buscar ayuda por un canal oficial.",
        "Desconfíe si alguien le pide instalar un programa o compartir la pantalla.",
        "No comparta conmigo contraseñas, códigos ni acceso remoto a su dispositivo.",
        "Puede cerrar esta llamada y buscar el contacto de soporte en el sitio oficial.",
        "Yo no necesito controlar su equipo para explicarle cómo pedir ayuda.",
    ],
    "E06": [
        "Le llamo por un paquete que supuestamente no pudieron entregar.",
        "También podría decirle que soy un familiar y que necesito ayuda urgente.",
        "No comparta datos de pago ni códigos con alguien que no pueda identificar.",
        "Puede llamar a su familiar usando un número que ya tenga guardado.",
        "Revise cualquier envío desde la aplicación o el sitio oficial de la paquetería.",
        "Usted puede terminar la llamada y confirmar la historia por separado.",
    ],
    "E07": [
        "Soy de atención a pensiones; le llamo por un supuesto problema con su próximo depósito.",
        "Quiero que lo resolvamos hoy, aunque usted puede tomarse el tiempo para verificar.",
        "No me comparta su número completo de cuenta ni otros datos personales.",
        "Busque el teléfono de atención en documentos oficiales que ya tenga.",
        "Si el aviso es legítimo, la institución podrá confirmarlo por sus canales habituales.",
        "Usted decide si continúa; puede colgar y llamar directamente a la institución.",
    ],
    "E08": [
        "Le llamo porque detecté un supuesto problema de acceso en una de sus cuentas.",
        "Quiero que permanezca en línea mientras usted decide cómo verificarlo.",
        "No abra enlaces ni instale aplicaciones que alguien le dicte durante una llamada.",
        "Nunca me comparta una contraseña o un código de verificación.",
        "Puede revisar su cuenta desde la aplicación que ya utiliza habitualmente.",
        "Si algo le parece extraño, cuelgue y contacte a la institución por un canal oficial.",
    ],
}

_NOMBRES_ESCENARIOS = {
    "E01": "Cargo no reconocido",
    "E02": "Bloqueo de tarjeta o pensión",
    "E03": "Cuenta de resguardo con CLABE ficticia",
    "E04": "Bono o apoyo pendiente",
    "E05": "Soporte técnico falso",
    "E06": "Familiar o paquete urgente",
    "E07": "Problema con depósito de pensión",
    "E08": "Alerta de acceso a cuenta",
}


def cargar_escenarios_voz() -> list[dict]:
    """Carga los escenarios E01-E08 desde data/scenarios/e01_e08_voice.json."""
    scenarios_path = (
        Path(__file__).resolve().parents[3]
        / "data"
        / "scenarios"
        / "e01_e08_voice.json"
    )
    if scenarios_path.exists():
        data = json.loads(scenarios_path.read_text(encoding="utf-8"))
        return [
            {
                "id": scenario.get("id", "E01"),
                "trap_id": scenario.get("trap_id"),
                "description": _NOMBRES_ESCENARIOS.get(
                    scenario.get("id"), "Simulación de llamada inesperada"
                ),
            }
            for scenario in data.get("scenarios", [])
            if isinstance(scenario, dict)
        ]
    return []


class BotEstafadorSimulator:
    """Simulador educativo automático, con guiones ficticios y límites estrictos."""

    def __init__(
        self,
        scenario_id: str = "E01",
        max_turns: int = DEFAULT_BOT_MAX_TURNS,
        max_duration_seconds: float = DEFAULT_MAX_DURATION_SECONDS,
        audio_engine: Optional[AudioEngine] = None,
        locked_avatar: AvatarId | str = AvatarId.LUPITA,
        locked_voice_profile: Optional[LockedVoiceProfile] = None,
    ) -> None:
        self.scenario_id = scenario_id
        self.max_turns = max(1, min(max_turns, MAX_BOT_TURNS_LIMIT))
        self.turn_index: int = 0
        self.stopped: bool = False

        escenario = next(
            (s for s in cargar_escenarios_voz() if s.get("id") == scenario_id),
            None,
        )
        self.description: str = (
            escenario.get("description", "Simulación bancaria")
            if escenario
            else "Estafa bancaria estándar (guion sintético)"
        )
        trap_id = escenario.get("trap_id") if escenario else "TRAP-SIM-BOT"
        self.guion = _GUIONES_SIMULACION_EDUCATIVA.get(
            scenario_id, _GUIONES_SIMULACION_EDUCATIVA["E01"]
        )[: self.max_turns]

        self.voice_service = VoiceService(
            max_duration_seconds=max(30.0, min(max_duration_seconds, 300.0)),
            audio_engine=audio_engine,
            trap_id=trap_id,
            locked_avatar=locked_avatar,
            locked_voice_profile=locked_voice_profile,
        )

    def iniciar(self) -> CallResult:
        """Inicia la sesión de simulación y devuelve el saludo de Lupita."""
        return self.voice_service.iniciar_llamada()

    @property
    def puede_avanzar(self) -> bool:
        """True si aún quedan turnos autorizables y la llamada sigue activa."""
        return (
            not self.stopped
            and self.voice_service.activa
            and self.turn_index < len(self.guion)
            and self.turn_index < self.max_turns
        )

    async def siguiente_turno(self) -> tuple[Optional[str], CallResult]:
        """
        Ejecuta un turno del guion educativo y la respuesta de Doña Lupita.
        """
        if not self.puede_avanzar:
            if self.voice_service.activa and self.turn_index >= self.max_turns:
                self.voice_service.estado.status = CallStatus.COMPLETED
            res = self.voice_service._build_result(
                respuesta_texto="[Simulación finalizada: límite de turnos o llamada cerrada]",
                intencion=self.voice_service.estado.ultima_intencion(),
            )
            return None, res

        mensaje_estafador = self.guion[self.turn_index]
        self.turn_index += 1

        resultado_lupita = await self.voice_service.process_call(mensaje_estafador)
        if not self.puede_avanzar and self.voice_service.activa:
            self.voice_service.estado.status = CallStatus.COMPLETED
            resultado_lupita = self.voice_service._build_result(
                respuesta_texto=resultado_lupita.respuesta_texto,
                intencion=resultado_lupita.ultima_intencion,
                audio_ref=resultado_lupita.audio_ref,
                tts_texto=resultado_lupita.tts_texto,
            )
        return mensaje_estafador, resultado_lupita

    def detener(self) -> CallResult:
        """Detiene la simulación manualmente."""
        self.stopped = True
        return self.voice_service.colgar()


# ---------------------------------------------------------------------------
# CLI rápido para pruebas en consola
# ---------------------------------------------------------------------------

async def _cli_demo() -> None:
    """Demo interactiva en consola — modo texto."""
    print("=" * 60)
    print("  🎭 Doña Lupita — Demo en modo texto")
    print("  Escribe lo que diría el atacante. 'q' para salir.")
    print("=" * 60)

    service = VoiceService(max_duration_seconds=120)
    result = service.iniciar_llamada()
    print(f"\n🔊 Lupita: {result.respuesta_texto}\n")

    while service.activa:
        try:
            user_input = input("🎤 Atacante: ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if user_input.lower() in ("q", "quit", "exit", "colgar"):
            result = service.colgar()
            print(f"\n📞 {result.respuesta_texto}")
            break

        result = await service.process_call(user_input)
        print(f"\n🔊 Lupita [{result.ultima_intencion}]: {result.respuesta_texto}")

        if result.tts_texto:
            print(f"   🗣️  (TTS dinámico): {result.tts_texto}")

        if result.indicadores:
            for ind in result.indicadores:
                estado_dv = "✅" if ind.digito_verificador_ok else "❌" if ind.digito_verificador_ok is False else "⏳"
                print(f"   📋 {ind.tipo}: {ind.valor_enmascarado} [{ind.confianza}] DV:{estado_dv}")

        print(f"   ⏱️  {result.duracion_segundos:.1f}s / {service.max_duration_seconds}s")
        print(f"   📌 Estado: {result.status}\n")

    print("\n--- Transcripción completa ---")
    print(result.transcripcion_completa)
    print(f"\n--- Indicadores finales: {len(result.indicadores)} ---")
    for ind in result.indicadores:
        print(f"  • {ind.tipo}: {ind.valor} (confianza: {ind.confianza}, fuentes: {ind.fuentes})")


if __name__ == "__main__":
    asyncio.run(_cli_demo())
