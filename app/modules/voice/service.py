"""
service.py — Servicio principal del módulo de voz (Doña Lupita).

Función principal: process_call(input) -> CallResult
Orquesta el flujo completo: recibe texto/audio, selecciona intención,
genera respuesta, extrae indicadores y controla duración.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional

from app.modules.voice.audio_engine import AudioEngine, TextInputAdapter
from app.modules.voice.clabe_extractor import (
    extraer_clabe,
    formatear_digitos_para_voz,
    palabras_a_digitos,
    validar_digito_verificador_clabe,
)
from app.modules.voice.models import (
    CallResult,
    CallStatus,
    EstadoConversacion,
    IndicadorCandidato,
    Intencion,
    NivelConfianza,
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
    ) -> None:
        self.max_duration_seconds = max_duration_seconds
        self.usar_ollama = usar_ollama
        self.ollama_timeout_ms = ollama_timeout_ms
        self.audio_engine = audio_engine or AudioEngine()
        self.trap_id = trap_id

        # Estado mutable de la sesión
        self.estado = EstadoConversacion()
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

    # -------------------------------------------------------------------
    # Inicio y fin de llamada
    # -------------------------------------------------------------------

    def iniciar_llamada(self) -> CallResult:
        """Inicia la sesión de llamada. Devuelve el saludo inicial de Lupita."""
        self._start_time = time.monotonic()
        self.estado = EstadoConversacion()
        self.estado.status = CallStatus.ACTIVE

        saludo = "¡Bueno! ¿Quién habla? Aquí es casa de Doña Lupita..."
        self.estado.agregar_turno("lupita", saludo, Intencion.ASUSTARSE)

        return self._build_result(
            respuesta_texto=saludo,
            audio_ref="saludo_01.mp3",
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
            respuesta = respuesta_anti_injection()
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
