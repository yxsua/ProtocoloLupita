"""
models.py — Esquemas de datos para el módulo de voz (Doña Lupita).

Define los tipos de datos centrales: intenciones permitidas, resultado de llamada,
indicadores candidatos y estado de la conversación.
Compatible con el contrato común: Event, Indicator del core.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Intenciones cerradas (lista fija, 6 elementos)
# ---------------------------------------------------------------------------

class Intencion(str, Enum):
    """Lista cerrada de intenciones que Doña Lupita puede ejecutar."""
    ASUSTARSE = "asustarse"
    PEDIR_REPETICION = "pedir_repeticion"
    PREGUNTAR_CUENTA_DEPOSITO = "preguntar_cuenta_deposito"
    REPETIR_DIGITOS = "repetir_digitos"
    DAR_LARGAS = "dar_largas"
    DESPEDIRSE = "despedirse"


# ---------------------------------------------------------------------------
# Estado de finalización de la llamada
# ---------------------------------------------------------------------------

class CallStatus(str, Enum):
    """Estado de finalización de la llamada."""
    ACTIVE = "active"
    TIMEOUT = "timeout"
    USER_HANGUP = "user_hangup"
    COMPLETED = "completed"


class AvatarId(str, Enum):
    """Identidades ciudadanas disponibles para una llamada."""

    LUPITA = "lupita"
    RAMIRO = "ramiro"
    CARMEN = "carmen"
    HECTOR = "hector"


class SpeakerVoiceProfile(BaseModel):
    """Configuración exacta de voz fijada para un interlocutor."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: Literal["speechSynthesis", "piper", "pregrabado"] = "speechSynthesis"
    voice_uri: str = Field(default="", max_length=512)
    voice_name: str = Field(default="", max_length=256)
    lang: str = Field(default="es-MX", max_length=32)
    rate: float = Field(default=0.9, ge=0.5, le=2.0)
    pitch: float = Field(default=1.0, ge=0.5, le=2.0)


class LockedVoiceProfile(BaseModel):
    """Perfiles inmutables de ciudadano y Bot Estafador para una sesión."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    citizen: SpeakerVoiceProfile
    attacker: SpeakerVoiceProfile


# ---------------------------------------------------------------------------
# Nivel de confianza para indicadores
# ---------------------------------------------------------------------------

class NivelConfianza(str, Enum):
    """Nivel de confianza de un indicador candidato."""
    ALTA = "alta"            # Confirmación cruzada de múltiples fuentes
    MEDIA = "media"          # Confirmación parcial (ej. repetición exitosa)
    BAJA = "baja"            # Fuente única sin confirmación cruzada
    SIN_VERIFICAR = "sin_verificar"


# ---------------------------------------------------------------------------
# Indicador candidato (ej. CLABE detectada)
# ---------------------------------------------------------------------------

class IndicadorCandidato(BaseModel):
    """Un indicador extraído durante la conversación (CLABE, teléfono, etc.)."""
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    tipo: str = Field(..., description="Tipo de indicador: clabe | telefono | cuenta | otro")
    valor: str = Field(..., description="Valor extraído (dígitos o texto normalizado)")
    valor_enmascarado: str = Field(
        default="",
        description="Valor parcialmente oculto para la interfaz"
    )
    confianza: NivelConfianza = NivelConfianza.SIN_VERIFICAR
    fuentes: list[str] = Field(
        default_factory=list,
        description="Lista de fuentes que aportaron este valor (ej. 'dictado_1', 'dictado_2')"
    )
    digito_verificador_ok: Optional[bool] = Field(
        default=None,
        description="Resultado de la validación del dígito verificador (solo para CLABE)"
    )

    def enmascarar(self) -> str:
        """Genera versión enmascarada del valor (muestra primeros 3 y últimos 4)."""
        if len(self.valor) >= 8:
            self.valor_enmascarado = self.valor[:3] + "*" * (len(self.valor) - 7) + self.valor[-4:]
        else:
            self.valor_enmascarado = "*" * len(self.valor)
        return self.valor_enmascarado

    def es_fuente_unica(self) -> bool:
        """True si el indicador proviene de una sola fuente sin confirmación cruzada."""
        return len(self.fuentes) <= 1


# ---------------------------------------------------------------------------
# Turno de conversación
# ---------------------------------------------------------------------------

class TurnoConversacion(BaseModel):
    """Un turno individual en la conversación (usuario o Lupita)."""
    rol: str = Field(..., description="'usuario' o 'lupita'")
    texto: str
    intencion: Optional[Intencion] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Estado de la conversación (en memoria)
# ---------------------------------------------------------------------------

class EstadoConversacion(BaseModel):
    """Estado mutable de la conversación activa."""
    locked_avatar: AvatarId = AvatarId.LUPITA
    locked_voice_profile: Optional[LockedVoiceProfile] = None
    turnos: list[TurnoConversacion] = Field(default_factory=list)
    indicadores: list[IndicadorCandidato] = Field(default_factory=list)
    clabe_pendiente: Optional[str] = Field(
        default=None,
        description="CLABE parcial que se está recopilando dígito a dígito"
    )
    confirmaciones_pendientes: int = Field(
        default=0,
        description="Número de veces que se ha pedido repetir la CLABE"
    )
    duracion_segundos: float = 0.0
    status: CallStatus = CallStatus.ACTIVE

    def agregar_turno(self, rol: str, texto: str, intencion: Optional[Intencion] = None) -> None:
        self.turnos.append(TurnoConversacion(rol=rol, texto=texto, intencion=intencion))

    def ultima_intencion(self) -> Optional[Intencion]:
        """Devuelve la última intención de Lupita, si existe."""
        for turno in reversed(self.turnos):
            if turno.rol == "lupita" and turno.intencion is not None:
                return turno.intencion
        return None


# ---------------------------------------------------------------------------
# CallResult — contrato principal de salida
# ---------------------------------------------------------------------------

class CallResult(BaseModel):
    """
    Resultado de process_call().
    Contrato de integración: contiene toda la información de la llamada
    sin incluir audio crudo.
    """
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:16])
    transcripcion_completa: str = Field(
        default="",
        description="Transcripción consolidada de toda la conversación"
    )
    ultima_intencion: Optional[Intencion] = None
    indicadores: list[IndicadorCandidato] = Field(default_factory=list)
    duracion_segundos: float = 0.0
    status: CallStatus = CallStatus.ACTIVE
    locked_avatar: AvatarId = AvatarId.LUPITA
    locked_voice_profile: Optional[LockedVoiceProfile] = None
    trap_id: Optional[str] = Field(
        default=None,
        description="Identificador del número trampa receptor para atribución"
    )
    evento_ref: Optional[str] = Field(
        default=None,
        description="Referencia al Event del core (ID del evento persistido)"
    )
    timestamp_inicio: datetime = Field(default_factory=datetime.utcnow)
    timestamp_fin: Optional[datetime] = None

    # Campos de respuesta para el turno actual
    respuesta_texto: str = Field(
        default="",
        description="Texto que Lupita debe decir/mostrar en este turno"
    )
    audio_ref: Optional[str] = Field(
        default=None,
        description="Referencia al fragmento de audio pregrabado (nombre de archivo)"
    )
    tts_texto: Optional[str] = Field(
        default=None,
        description="Texto para síntesis dinámica con Piper (solo contenido dinámico)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "id": "abc123def456",
                "transcripcion_completa": "Atacante: Señora necesito su cuenta...",
                "ultima_intencion": "preguntar_cuenta_deposito",
                "indicadores": [],
                "duracion_segundos": 45.2,
                "status": "active",
                "evento_ref": None,
                "respuesta_texto": "¿Mande? ¿Y eso en qué cuenta me lo depositan?",
                "audio_ref": "preguntar_cuenta_deposito_01.wav",
                "tts_texto": None,
            }
        }
