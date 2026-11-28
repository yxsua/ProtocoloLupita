"""
audio_engine.py — Motor de audio completo: Whisper local (STT), Piper (TTS),
                   captura de micrófono y reproductor.

Arquitectura:
  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
  │ AudioCapture │────▶│ SpeechToText │────▶│  (texto)     │
  │ (micrófono)  │     │ (Whisper)    │     │              │
  └──────────────┘     └──────────────┘     └──────────────┘

  ┌──────────────┐     ┌──────────────┐
  │ TextToSpeech │────▶│ AudioPlayer  │
  │ (Piper)      │     │ (reproduce)  │
  └──────────────┘     └──────────────┘

Cada componente tiene:
  - Interfaz abstracta (ABC)
  - Implementación real (Whisper/Piper/sounddevice)
  - Stub de respaldo (modo texto, sin hardware)

El AudioEngine unificado detecta qué está disponible y degrada con gracia.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import struct
import subprocess
import tempfile
import wave
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constantes de audio
# ---------------------------------------------------------------------------
SAMPLE_RATE = 16000      # Whisper espera 16 kHz
CHANNELS = 1             # Mono
SAMPLE_WIDTH = 2         # 16-bit PCM (2 bytes)
CHUNK_DURATION_S = 0.5   # Fragmento de captura en segundos
SILENCE_THRESHOLD = 500  # Umbral RMS para detectar silencio


# ═══════════════════════════════════════════════════════════════════════════
#  1. CAPTURA DE AUDIO (MICRÓFONO)
# ═══════════════════════════════════════════════════════════════════════════

class AudioCapture(ABC):
    """Interfaz para captura de audio desde micrófono."""

    @abstractmethod
    async def start(self) -> None:
        """Inicia la captura de audio."""

    @abstractmethod
    async def stop(self) -> bytes:
        """Detiene la captura y devuelve el audio en WAV bytes."""

    @abstractmethod
    async def is_recording(self) -> bool:
        """True si está grabando."""


class MicrophoneCapture(AudioCapture):
    """
    Captura real desde micrófono usando sounddevice.

    Graba a 16 kHz mono (formato requerido por Whisper).
    Acumula fragmentos en memoria y los devuelve como WAV al detener.
    """

    def __init__(self, sample_rate: int = SAMPLE_RATE, channels: int = CHANNELS) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._recording = False
        self._frames: list[bytes] = []
        self._stream = None

    async def start(self) -> None:
        try:
            import sounddevice as sd
        except ImportError:
            raise RuntimeError(
                "sounddevice no está instalado. "
                "Instálalo con: pip install sounddevice"
            )

        self._frames = []
        self._recording = True
        chunk_size = int(self._sample_rate * CHUNK_DURATION_S)

        def _callback(indata, frames, time_info, status):
            if status:
                logger.warning(f"[Mic] Estado de captura: {status}")
            if self._recording:
                self._frames.append(bytes(indata))

        self._stream = sd.RawInputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="int16",
            blocksize=chunk_size,
            callback=_callback,
        )
        self._stream.start()
        logger.info(
            f"[Mic] Captura iniciada: {self._sample_rate} Hz, "
            f"{self._channels} ch, chunks de {chunk_size} muestras"
        )

    async def stop(self) -> bytes:
        self._recording = False
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        if not self._frames:
            logger.warning("[Mic] No se capturaron frames")
            return b""

        raw_audio = b"".join(self._frames)
        self._frames = []

        # Empaquetar como WAV en memoria
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wf:
            wf.setnchannels(self._channels)
            wf.setsampwidth(SAMPLE_WIDTH)
            wf.setframerate(self._sample_rate)
            wf.writeframes(raw_audio)

        wav_bytes = wav_buffer.getvalue()
        duration_s = len(raw_audio) / (self._sample_rate * SAMPLE_WIDTH * self._channels)
        logger.info(f"[Mic] Captura detenida: {duration_s:.1f}s, {len(wav_bytes)} bytes WAV")
        return wav_bytes

    async def is_recording(self) -> bool:
        return self._recording


class WebAudioCapture(AudioCapture):
    """
    Adaptador que recibe audio desde el navegador (WebSocket/POST).

    En lugar de acceder al micrófono directamente, recibe los bytes WAV
    que el frontend captura con MediaRecorder / Web Audio API.
    """

    def __init__(self) -> None:
        self._recording = False
        self._audio_buffer: bytes = b""

    def feed_audio(self, wav_data: bytes) -> None:
        """Alimenta con audio recibido del frontend."""
        self._audio_buffer = wav_data

    async def start(self) -> None:
        self._recording = True
        self._audio_buffer = b""
        logger.info("[WebAudio] Esperando audio del navegador...")

    async def stop(self) -> bytes:
        self._recording = False
        result = self._audio_buffer
        self._audio_buffer = b""
        logger.info(f"[WebAudio] Audio recibido: {len(result)} bytes")
        return result

    async def is_recording(self) -> bool:
        return self._recording


class StubAudioCapture(AudioCapture):
    """Stub para modo texto — no captura audio real."""

    def __init__(self) -> None:
        self._recording = False

    async def start(self) -> None:
        self._recording = True
        logger.info("[StubCapture] Captura iniciada (stub)")

    async def stop(self) -> bytes:
        self._recording = False
        logger.info("[StubCapture] Captura detenida (stub)")
        return b""

    async def is_recording(self) -> bool:
        return self._recording


# ═══════════════════════════════════════════════════════════════════════════
#  2. TRANSCRIPCIÓN (STT — Whisper local)
# ═══════════════════════════════════════════════════════════════════════════

class SpeechToText(ABC):
    """Interfaz para transcripción de audio a texto."""

    @abstractmethod
    async def transcribe(self, audio_data: bytes) -> str:
        """Transcribe audio (WAV bytes) a texto."""

    @abstractmethod
    def is_available(self) -> bool:
        """True si el modelo STT está cargado y disponible."""


class WhisperSTT(SpeechToText):
    """
    Transcripción offline con OpenAI Whisper (local).

    Usa el paquete `whisper` (openai-whisper) con un modelo descargado
    previamente. Se ejecuta en un thread pool para no bloquear el event loop.

    Modelos sugeridos (descargar antes del hackathon):
      - "tiny"   (~39M)  — más rápido, menor calidad
      - "base"   (~74M)  — buen balance
      - "small"  (~244M) — mejor calidad, más lento
    """

    def __init__(
        self,
        model_name: str = "base",
        language: str = "es",
        device: str = "cpu",
    ) -> None:
        self._model_name = model_name
        self._language = language
        self._device = device
        self._model = None
        self._available = False
        self._loading = False

    def load_model(self) -> bool:
        """Carga el modelo Whisper. Llamar una sola vez al inicio."""
        if self._model is not None:
            return True
        try:
            import whisper  # type: ignore[import-untyped]
            logger.info(f"[Whisper] Cargando modelo '{self._model_name}' en {self._device}...")
            self._model = whisper.load_model(self._model_name, device=self._device)
            self._available = True
            logger.info(f"[Whisper] Modelo '{self._model_name}' cargado exitosamente")
            return True
        except ImportError:
            logger.error(
                "[Whisper] openai-whisper no está instalado. "
                "Instálalo con: pip install openai-whisper"
            )
            self._available = False
            return False
        except Exception as e:
            logger.error(f"[Whisper] Error cargando modelo: {e}")
            self._available = False
            return False

    async def transcribe(self, audio_data: bytes) -> str:
        """
        Transcribe audio WAV a texto usando Whisper local.

        El procesamiento pesado corre en un thread pool (run_in_executor)
        para no bloquear el event loop de asyncio.
        """
        if not self._available or self._model is None:
            if not self.load_model():
                logger.warning("[Whisper] Modelo no disponible, devolviendo vacío")
                return ""

        if not audio_data:
            return ""

        loop = asyncio.get_event_loop()
        try:
            result = await loop.run_in_executor(None, self._transcribe_sync, audio_data)
            return result
        except Exception as e:
            logger.error(f"[Whisper] Error en transcripción: {e}")
            return ""

    def _transcribe_sync(self, audio_data: bytes) -> str:
        """Transcripción síncrona (se ejecuta en thread pool)."""
        import whisper  # type: ignore[import-untyped]
        import numpy as np  # type: ignore[import-untyped]

        # Decodificar WAV a numpy array float32 normalizado
        audio_np = self._wav_bytes_to_numpy(audio_data)
        if audio_np is None or len(audio_np) == 0:
            return ""

        # Detectar si es puro silencio
        rms = float(np.sqrt(np.mean(audio_np ** 2)))
        if rms < 0.005:
            logger.info("[Whisper] Audio detectado como silencio")
            return ""

        # Transcribir
        result = self._model.transcribe(
            audio_np,
            language=self._language,
            fp16=False,  # CPU no soporta fp16
            task="transcribe",
        )

        text = result.get("text", "").strip()
        logger.info(f"[Whisper] Transcripción: '{text[:80]}...' " if len(text) > 80 else f"[Whisper] Transcripción: '{text}'")
        return text

    @staticmethod
    def _wav_bytes_to_numpy(wav_data: bytes):
        """Convierte bytes WAV a numpy array float32 normalizado [-1, 1]."""
        try:
            import numpy as np  # type: ignore[import-untyped]

            wav_io = io.BytesIO(wav_data)
            with wave.open(wav_io, "rb") as wf:
                n_channels = wf.getnchannels()
                sampwidth = wf.getsampwidth()
                framerate = wf.getframerate()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)

            # Convertir a int16
            if sampwidth == 2:
                samples = np.frombuffer(raw, dtype=np.int16)
            elif sampwidth == 4:
                samples = np.frombuffer(raw, dtype=np.int32).astype(np.int16)
            else:
                # Intentar como int16
                samples = np.frombuffer(raw, dtype=np.int16)

            # Si es estéreo, tomar solo canal izquierdo
            if n_channels > 1:
                samples = samples[::n_channels]

            # Normalizar a float32 [-1, 1]
            audio_float = samples.astype(np.float32) / 32768.0

            # Resamplear a 16 kHz si es necesario
            if framerate != SAMPLE_RATE:
                duration = len(audio_float) / framerate
                target_len = int(duration * SAMPLE_RATE)
                indices = np.linspace(0, len(audio_float) - 1, target_len).astype(int)
                audio_float = audio_float[indices]

            return audio_float

        except Exception as e:
            logger.error(f"[Whisper] Error decodificando WAV: {e}")
            return None

    def is_available(self) -> bool:
        return self._available


class StubSpeechToText(SpeechToText):
    """Stub para modo texto — no transcribe audio real."""

    def __init__(self) -> None:
        self._available = True

    async def transcribe(self, audio_data: bytes) -> str:
        logger.info("[StubSTT] Transcripción solicitada (stub — devuelve vacío)")
        return ""

    def is_available(self) -> bool:
        return self._available


class TextInputAdapter(SpeechToText):
    """
    Adaptador de texto directo (modo texto de respaldo).
    Se usa cuando Whisper no está disponible o no hay micrófono.
    """

    def __init__(self) -> None:
        self._next_text: Optional[str] = None

    def set_text(self, text: str) -> None:
        """Establece el texto para la siguiente 'transcripción'."""
        self._next_text = text

    async def transcribe(self, audio_data: bytes) -> str:
        result = self._next_text or ""
        self._next_text = None
        return result

    def is_available(self) -> bool:
        return True


# ═══════════════════════════════════════════════════════════════════════════
#  3. REPRODUCCIÓN DE AUDIO PREGRABADO
# ═══════════════════════════════════════════════════════════════════════════

class AudioPlayer(ABC):
    """Interfaz para reproducción de fragmentos de audio."""

    @abstractmethod
    async def play(self, file_path: str) -> None:
        """Reproduce un archivo de audio."""

    @abstractmethod
    async def play_waiting(self) -> None:
        """Reproduce audio de espera / relleno."""

    @abstractmethod
    async def stop(self) -> None:
        """Detiene la reproducción actual."""

    @abstractmethod
    async def play_bytes(self, wav_data: bytes) -> None:
        """Reproduce audio desde bytes WAV (para TTS dinámico)."""


class SounddevicePlayer(AudioPlayer):
    """
    Reproductor real usando sounddevice.
    Reproduce WAV en un thread para no bloquear asyncio.
    """

    def __init__(self, assets_dir: Optional[Path] = None) -> None:
        self._assets_dir = assets_dir or Path(__file__).parent / "assets"
        self._playing = False

    async def play(self, file_path: str) -> None:
        path = Path(file_path)
        if not path.exists():
            logger.warning(f"[Player] Archivo no encontrado: {file_path}")
            return

        try:
            import sounddevice as sd  # type: ignore[import-untyped]
            import numpy as np  # type: ignore[import-untyped]

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._play_file_sync, str(path))
        except ImportError:
            logger.warning("[Player] sounddevice no disponible para reproducción")
        except Exception as e:
            logger.error(f"[Player] Error reproduciendo {file_path}: {e}")

    def _play_file_sync(self, file_path: str) -> None:
        import sounddevice as sd  # type: ignore[import-untyped]
        import numpy as np  # type: ignore[import-untyped]

        with wave.open(file_path, "rb") as wf:
            framerate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        self._playing = True
        sd.play(samples, samplerate=framerate)
        sd.wait()
        self._playing = False

    async def play_waiting(self) -> None:
        waiting_files = list(self._assets_dir.glob("espera_*.wav"))
        if waiting_files:
            import random
            await self.play(str(random.choice(waiting_files)))
        else:
            logger.info("[Player] No hay audios de espera disponibles")

    async def stop(self) -> None:
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
            sd.stop()
            self._playing = False
        except ImportError:
            pass

    async def play_bytes(self, wav_data: bytes) -> None:
        if not wav_data:
            return
        try:
            import sounddevice as sd  # type: ignore[import-untyped]
            import numpy as np  # type: ignore[import-untyped]

            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._play_bytes_sync, wav_data)
        except ImportError:
            logger.warning("[Player] sounddevice no disponible")

    def _play_bytes_sync(self, wav_data: bytes) -> None:
        import sounddevice as sd  # type: ignore[import-untyped]
        import numpy as np  # type: ignore[import-untyped]

        wav_io = io.BytesIO(wav_data)
        with wave.open(wav_io, "rb") as wf:
            framerate = wf.getframerate()
            raw = wf.readframes(wf.getnframes())
            samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0

        self._playing = True
        sd.play(samples, samplerate=framerate)
        sd.wait()
        self._playing = False


class WebAudioPlayer(AudioPlayer):
    """
    Reproductor para el frontend web.

    No reproduce localmente — devuelve la referencia del archivo o los bytes
    WAV para que el frontend los reproduzca vía <audio> o Web Audio API.
    """

    def __init__(self) -> None:
        self._last_audio_ref: Optional[str] = None
        self._last_audio_bytes: Optional[bytes] = None

    async def play(self, file_path: str) -> None:
        self._last_audio_ref = file_path
        logger.info(f"[WebPlayer] Audio listo para frontend: {file_path}")

    async def play_waiting(self) -> None:
        self._last_audio_ref = "_waiting"
        logger.info("[WebPlayer] Audio de espera listo para frontend")

    async def stop(self) -> None:
        self._last_audio_ref = None
        self._last_audio_bytes = None

    async def play_bytes(self, wav_data: bytes) -> None:
        self._last_audio_bytes = wav_data
        logger.info(f"[WebPlayer] Audio TTS listo: {len(wav_data)} bytes")

    @property
    def pending_audio_ref(self) -> Optional[str]:
        ref = self._last_audio_ref
        self._last_audio_ref = None
        return ref

    @property
    def pending_audio_bytes(self) -> Optional[bytes]:
        data = self._last_audio_bytes
        self._last_audio_bytes = None
        return data


class StubAudioPlayer(AudioPlayer):
    """Stub para modo texto — no reproduce audio real."""

    async def play(self, file_path: str) -> None:
        logger.info(f"[StubPlayer] Reproduciendo (stub): {file_path}")

    async def play_waiting(self) -> None:
        logger.info("[StubPlayer] Audio de espera (stub)")

    async def stop(self) -> None:
        logger.info("[StubPlayer] Detenido (stub)")

    async def play_bytes(self, wav_data: bytes) -> None:
        logger.info(f"[StubPlayer] Reproduciendo bytes (stub): {len(wav_data)} bytes")


# ═══════════════════════════════════════════════════════════════════════════
#  4. SÍNTESIS DE VOZ (TTS — Piper local)
# ═══════════════════════════════════════════════════════════════════════════

class TextToSpeech(ABC):
    """Interfaz para síntesis de texto a voz."""

    @abstractmethod
    async def synthesize(self, text: str) -> bytes:
        """Sintetiza texto a audio WAV bytes."""

    @abstractmethod
    def is_available(self) -> bool:
        """True si el motor TTS está disponible."""


class PiperTTS(TextToSpeech):
    """
    Síntesis de voz local con Piper TTS.

    Piper es un motor TTS rápido y ligero que corre offline.
    Se invoca como proceso externo: `piper --model <model> --output_file -`

    Modelos en español sugeridos (descargar antes del hackathon):
      - es_ES-sharvard-medium
      - es_MX-ald-medium (mexicano)
      - es_ES-mls_10246-low

    Instalación:
      pip install piper-tts
      # O descargar el binario de https://github.com/rhasspy/piper/releases
    """

    def __init__(
        self,
        model_path: Optional[str] = None,
        piper_binary: str = "piper",
        speaker_id: Optional[int] = None,
        length_scale: float = 1.0,
    ) -> None:
        self._model_path = model_path
        self._piper_cmd: list[str] = [piper_binary]
        self._speaker_id = speaker_id
        self._length_scale = length_scale
        self._available: Optional[bool] = None

    def _check_availability(self) -> bool:
        """Verifica si Piper está instalado y el modelo existe."""
        import sys

        # Verificar binario
        try:
            result = subprocess.run(
                [*self._piper_cmd, "--version"],
                capture_output=True, text=True, timeout=5,
            )
            binary_ok = result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            # Intentar como módulo Python
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "piper", "--version"],
                    capture_output=True, text=True, timeout=5,
                )
                if result.returncode == 0:
                    self._piper_cmd = [sys.executable, "-m", "piper"]
                    binary_ok = True
                else:
                    binary_ok = False
            except (FileNotFoundError, subprocess.TimeoutExpired):
                binary_ok = False

        # Verificar modelo
        model_ok = True
        if self._model_path:
            model_ok = Path(self._model_path).exists()
            if not model_ok:
                logger.warning(f"[Piper] Modelo no encontrado: {self._model_path}")

        self._available = binary_ok and model_ok
        if self._available:
            logger.info(f"[Piper] Disponible (modelo: {self._model_path or 'default'})")
        else:
            logger.warning(f"[Piper] No disponible (binario: {binary_ok}, modelo: {model_ok})")
        return self._available

    async def synthesize(self, text: str) -> bytes:
        """
        Sintetiza texto a WAV usando Piper.

        Corre en un thread pool para no bloquear asyncio.
        """
        if not self.is_available():
            logger.warning("[Piper] No disponible, no se puede sintetizar")
            return b""

        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, self._synthesize_sync, text)
        except Exception as e:
            logger.error(f"[Piper] Error en síntesis: {e}")
            return b""

    def _synthesize_sync(self, text: str) -> bytes:
        """Síntesis síncrona (se ejecuta en thread pool)."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            output_path = tmp.name

        cmd = [*self._piper_cmd]

        if self._model_path:
            cmd.extend(["--model", self._model_path])

        if self._speaker_id is not None:
            cmd.extend(["--speaker", str(self._speaker_id)])

        cmd.extend([
            "--length-scale", str(self._length_scale),
            "--output_file", output_path,
        ])

        try:
            proc = subprocess.run(
                cmd,
                input=text,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if proc.returncode != 0:
                logger.error(f"[Piper] Error (código {proc.returncode}): {proc.stderr[:200]}")
                return b""

            output = Path(output_path)
            if output.exists():
                wav_data = output.read_bytes()
                output.unlink(missing_ok=True)
                logger.info(f"[Piper] Sintetizado: {len(wav_data)} bytes, texto: '{text[:50]}'")
                return wav_data
            else:
                logger.error("[Piper] Archivo de salida no generado")
                return b""

        except subprocess.TimeoutExpired:
            logger.error("[Piper] Timeout en síntesis (>30s)")
            return b""
        except Exception as e:
            logger.error(f"[Piper] Error inesperado: {e}")
            return b""
        finally:
            Path(output_path).unlink(missing_ok=True)

    def is_available(self) -> bool:
        if self._available is None:
            self._check_availability()
        return self._available or False


class StubTextToSpeech(TextToSpeech):
    """Stub para modo texto — no sintetiza audio real."""

    async def synthesize(self, text: str) -> bytes:
        logger.info(f"[StubTTS] Síntesis solicitada (stub): {text[:50]}...")
        return b""

    def is_available(self) -> bool:
        return False


# ═══════════════════════════════════════════════════════════════════════════
#  5. UTILIDADES DE AUDIO
# ═══════════════════════════════════════════════════════════════════════════

def calcular_rms(audio_data: bytes) -> float:
    """Calcula el RMS (Root Mean Square) de audio PCM 16-bit."""
    if len(audio_data) < 2:
        return 0.0
    n_samples = len(audio_data) // 2
    samples = struct.unpack(f"<{n_samples}h", audio_data[:n_samples * 2])
    if not samples:
        return 0.0
    rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
    return rms


def detectar_silencio(audio_data: bytes, threshold: float = SILENCE_THRESHOLD) -> bool:
    """True si el audio es mayoritariamente silencio."""
    return calcular_rms(audio_data) < threshold


def wav_duration_seconds(wav_data: bytes) -> float:
    """Calcula la duración en segundos de un archivo WAV."""
    try:
        wav_io = io.BytesIO(wav_data)
        with wave.open(wav_io, "rb") as wf:
            return wf.getnframes() / wf.getframerate()
    except Exception:
        return 0.0


# ═══════════════════════════════════════════════════════════════════════════
#  6. MOTOR DE AUDIO UNIFICADO
# ═══════════════════════════════════════════════════════════════════════════

class AudioEngine:
    """
    Motor de audio que coordina captura, transcripción, reproducción y síntesis.

    Detecta automáticamente qué componentes están disponibles y degrada
    con gracia al modo texto cuando algo falta.

    Uso:
        # Modo automático (detecta hardware disponible)
        engine = AudioEngine.auto_detect()

        # Modo web (recibe audio del frontend)
        engine = AudioEngine.for_web()

        # Modo texto puro (sin audio)
        engine = AudioEngine()
    """

    def __init__(
        self,
        capture: Optional[AudioCapture] = None,
        stt: Optional[SpeechToText] = None,
        player: Optional[AudioPlayer] = None,
        tts: Optional[TextToSpeech] = None,
        assets_dir: Optional[str] = None,
    ) -> None:
        self.capture = capture or StubAudioCapture()
        self.stt = stt or StubSpeechToText()
        self.player = player or StubAudioPlayer()
        self.tts = tts or StubTextToSpeech()
        self.assets_dir = Path(assets_dir) if assets_dir else Path(__file__).parent / "assets"

    # -------------------------------------------------------------------
    # Factory methods
    # -------------------------------------------------------------------

    @classmethod
    def auto_detect(
        cls,
        whisper_model: str = "base",
        piper_model_path: Optional[str] = None,
        assets_dir: Optional[str] = None,
    ) -> "AudioEngine":
        """
        Crea un AudioEngine detectando automáticamente qué está disponible.

        Intenta activar: micrófono (sounddevice), Whisper, Piper.
        Si algo falla, usa el stub correspondiente.
        """
        # Captura
        capture: AudioCapture
        try:
            import sounddevice  # type: ignore[import-untyped]
            capture = MicrophoneCapture()
            logger.info("[AutoDetect] ✅ Micrófono disponible (sounddevice)")
        except ImportError:
            capture = StubAudioCapture()
            logger.info("[AutoDetect] ⚠️  sounddevice no disponible → stub")

        # STT
        stt: SpeechToText
        whisper_stt = WhisperSTT(model_name=whisper_model)
        if whisper_stt.load_model():
            stt = whisper_stt
            logger.info(f"[AutoDetect] ✅ Whisper '{whisper_model}' cargado")
        else:
            stt = StubSpeechToText()
            logger.info("[AutoDetect] ⚠️  Whisper no disponible → stub")

        # Player
        player: AudioPlayer
        try:
            import sounddevice  # type: ignore[import-untyped]
            player = SounddevicePlayer(
                assets_dir=Path(assets_dir) if assets_dir else None
            )
            logger.info("[AutoDetect] ✅ Reproductor disponible (sounddevice)")
        except ImportError:
            player = StubAudioPlayer()
            logger.info("[AutoDetect] ⚠️  Reproductor no disponible → stub")

        # TTS
        tts: TextToSpeech
        piper_tts = PiperTTS(model_path=piper_model_path)
        if piper_tts.is_available():
            tts = piper_tts
            logger.info("[AutoDetect] ✅ Piper TTS disponible")
        else:
            tts = StubTextToSpeech()
            logger.info("[AutoDetect] ⚠️  Piper TTS no disponible → stub")

        return cls(
            capture=capture, stt=stt, player=player, tts=tts,
            assets_dir=assets_dir,
        )

    @classmethod
    def for_web(
        cls,
        whisper_model: str = "base",
        piper_model_path: Optional[str] = None,
        assets_dir: Optional[str] = None,
    ) -> "AudioEngine":
        """
        Crea un AudioEngine optimizado para el frontend web.

        Usa WebAudioCapture y WebAudioPlayer; el audio viaja vía HTTP.
        Whisper y Piper corren en el servidor.
        """
        # Captura desde el navegador
        capture = WebAudioCapture()

        # STT — intentar Whisper
        stt: SpeechToText
        whisper_stt = WhisperSTT(model_name=whisper_model)
        if whisper_stt.load_model():
            stt = whisper_stt
        else:
            stt = TextInputAdapter()

        # Player web (devuelve refs al frontend)
        player = WebAudioPlayer()

        # TTS — intentar Piper
        tts: TextToSpeech
        piper_tts = PiperTTS(model_path=piper_model_path)
        if piper_tts.is_available():
            tts = piper_tts
        else:
            tts = StubTextToSpeech()

        return cls(
            capture=capture, stt=stt, player=player, tts=tts,
            assets_dir=assets_dir,
        )

    # -------------------------------------------------------------------
    # Propiedades
    # -------------------------------------------------------------------

    @property
    def modo_texto(self) -> bool:
        """True si estamos en modo texto (sin audio real)."""
        return isinstance(self.stt, (StubSpeechToText, TextInputAdapter))

    @property
    def whisper_disponible(self) -> bool:
        return isinstance(self.stt, WhisperSTT) and self.stt.is_available()

    @property
    def piper_disponible(self) -> bool:
        return isinstance(self.tts, PiperTTS) and self.tts.is_available()

    @property
    def microfono_disponible(self) -> bool:
        return isinstance(self.capture, (MicrophoneCapture, WebAudioCapture))

    def status(self) -> dict:
        """Estado de cada componente del motor de audio."""
        return {
            "microfono": self.microfono_disponible,
            "whisper": self.whisper_disponible,
            "piper": self.piper_disponible,
            "modo_texto": self.modo_texto,
            "capture_type": type(self.capture).__name__,
            "stt_type": type(self.stt).__name__,
            "player_type": type(self.player).__name__,
            "tts_type": type(self.tts).__name__,
        }

    # -------------------------------------------------------------------
    # Operaciones de alto nivel
    # -------------------------------------------------------------------

    async def transcribir_o_leer_texto(self, audio_data: bytes = b"") -> str:
        """Transcribe audio o devuelve el texto inyectado (modo respaldo)."""
        return await self.stt.transcribe(audio_data)

    async def reproducir_fragmento(self, intencion_audio_ref: Optional[str]) -> None:
        """Reproduce un fragmento pregrabado por referencia."""
        if intencion_audio_ref:
            ruta = self.assets_dir / intencion_audio_ref
            await self.player.play(str(ruta))

    async def sintetizar_dinamico(self, texto: str) -> Optional[bytes]:
        """Sintetiza texto con Piper TTS si está disponible."""
        if self.tts.is_available():
            return await self.tts.synthesize(texto)
        return None

    async def sintetizar_y_reproducir(self, texto: str) -> Optional[bytes]:
        """Sintetiza y reproduce dinámicamente. Devuelve los bytes WAV."""
        wav_data = await self.sintetizar_dinamico(texto)
        if wav_data:
            await self.player.play_bytes(wav_data)
        return wav_data

    async def reproducir_espera(self) -> None:
        """Reproduce audio de espera / relleno."""
        await self.player.play_waiting()

    async def capturar_y_transcribir(self) -> str:
        """Flujo completo: capturar audio → transcribir → devolver texto."""
        await self.capture.start()
        # La captura se detiene externamente (botón, timeout, etc.)
        # Este método devuelve la transcripción cuando se llame stop()
        audio_data = await self.capture.stop()
        if not audio_data:
            return ""
        return await self.stt.transcribe(audio_data)
