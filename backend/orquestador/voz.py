import asyncio
import gc
import logging
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Callable, Optional

import numpy as np

from .traspaso import TraspasoError
from .uploads import _Part, read_multipart

log = logging.getLogger("orquestador.voz")

MAX_AUDIO = 10 * 1024 * 1024
MAX_BODY_OVERHEAD = 64 * 1024
MAX_SECONDS = 120.0
TIMEOUT = 90.0
UPLOAD_TIMEOUT = 30.0
IDLE_SECONDS = 600.0
SAMPLE_RATE = 16000
BEAM_SIZE = 2
CPU_THREADS = 4
AUDIO_TYPES = {
    "audio/webm": "webm", "video/webm": "webm", "audio/mp4": "mp4", "video/mp4": "mp4", "audio/x-m4a": "mp4",
    "audio/ogg": "ogg", "audio/wav": "wav", "audio/x-wav": "wav", "audio/wave": "wav",
}
DEMUXERS = {"webm": "matroska", "mp4": "mov", "ogg": "ogg", "wav": "wav"}
MODEL_FILES = ("model.bin", "config.json", "tokenizer.json")
MODEL_MISSING = ("el modelo de voz no está descargado; corré `uv run orquestador descargar-modelo` "
                 "(es la única salida a internet de esta función)")


def sniff(head: bytes) -> Optional[str]:
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if head[4:8] == b"ftyp":
        return "mp4"
    if head.startswith(b"OggS"):
        return "ogg"
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "wav"
    return None


def decode(path: Path, max_seconds: Optional[float] = None, family: Optional[str] = None) -> np.ndarray:
    """Decodifica a 16 kHz mono float32 cortando apenas se pasa del tope: el header de duración no es de fiar."""
    import av

    max_seconds = MAX_SECONDS if max_seconds is None else max_seconds
    limit = int((max_seconds + 0.5) * SAMPLE_RATE)
    chunks: list = []
    count = 0
    try:
        # El demuxer queda fijado por la familia ya validada: ffmpeg no elige otro por sondeo.
        with av.open(str(path), mode="r", format=DEMUXERS.get(family) if family else None) as container:
            if not container.streams.audio:
                raise TraspasoError(415, "el archivo no tiene audio")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=SAMPLE_RATE)
            for frame in container.decode(audio=0):
                for out in resampler.resample(frame):
                    data = out.to_ndarray().reshape(-1)
                    count += data.size
                    if count > limit:
                        raise TraspasoError(413, f"el audio supera los {int(max_seconds)} segundos")
                    chunks.append(data)
            for out in resampler.resample(None):
                data = out.to_ndarray().reshape(-1)
                count += data.size
                chunks.append(data)
    except TraspasoError:
        raise
    except Exception:
        raise TraspasoError(415, "no se pudo decodificar el audio")
    if count > max_seconds * SAMPLE_RATE:
        raise TraspasoError(413, f"el audio supera los {int(max_seconds)} segundos")
    if not chunks:
        return np.zeros(0, dtype=np.float32)
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def trim_heap() -> None:
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def local_model_path(name: str, models_dir: Path) -> Path:
    """Resuelve el modelo solo desde disco: con un archivo faltante faster-whisper bajaría el tokenizer de internet."""
    candidate = Path(name)
    if candidate.is_dir():
        path = candidate
    else:
        from faster_whisper.utils import download_model as fetch

        path = Path(fetch(name, local_files_only=True, cache_dir=str(models_dir)))
    missing = [f for f in MODEL_FILES if not (path / f).is_file()]
    if missing:
        raise FileNotFoundError(", ".join(missing))
    return path


def load_model(name: str, models_dir: Path):
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    from faster_whisper import WhisperModel

    try:
        import onnxruntime

        onnxruntime.disable_telemetry_events()
    except Exception:
        log.warning("no se pudo desactivar la telemetría de onnxruntime")
    try:
        path = local_model_path(name, models_dir)
        return WhisperModel(str(path), device="cpu", compute_type="int8", cpu_threads=CPU_THREADS,
                            local_files_only=True)
    except Exception as exc:
        log.warning("no se pudo cargar el modelo de voz: %s", type(exc).__name__)
        raise TraspasoError(503, MODEL_MISSING)


def download_model(name: str, models_dir: Path) -> Path:
    from faster_whisper.utils import download_model as fetch

    models_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(models_dir, 0o700)
    return Path(fetch(name, cache_dir=str(models_dir)))


class VozService:
    """Una transcripción a la vez: si hay otra en curso responde 409 (sin cola, el front lo muestra y reintenta)."""

    def __init__(self, enabled: bool, model_name: str, data_dir: Path, model_factory: Optional[Callable] = None,
                 idle_seconds: float = IDLE_SECONDS, timeout: float = TIMEOUT, call_later: Optional[Callable] = None,
                 clock: Callable = time.monotonic):
        self.enabled = enabled
        self.model_name = model_name
        self.models_dir = data_dir / "models"
        self.tmp_dir = data_dir / "voz-tmp"
        self.factory = model_factory or (lambda name: load_model(name, self.models_dir))
        self.idle_seconds = idle_seconds
        self.timeout = timeout
        self.call_later = call_later
        self.clock = clock
        self.model = None
        self.busy = False
        self._timer = None
        self._model_lock = threading.Lock()
        self.sweep()

    def sweep(self) -> None:
        if not self.tmp_dir.is_dir():
            return
        for entry in self.tmp_dir.iterdir():
            try:
                if entry.is_file() or entry.is_symlink():
                    entry.unlink()
            except OSError:
                continue

    def estado(self) -> dict:
        return {"habilitada": self.enabled, "modelo": self.model_name, "cargado": self.model is not None,
                "ocupada": self.busy, "max_segundos": int(MAX_SECONDS)}

    def _schedule_unload(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None
        scheduler = self.call_later or asyncio.get_running_loop().call_later
        self._timer = scheduler(self.idle_seconds, self._unload)

    def _unload(self) -> None:
        self._timer = None
        if self.busy:
            self._schedule_unload()
            return
        with self._model_lock:
            self.model = None
        gc.collect()
        trim_heap()
        log.info("modelo de voz descargado de memoria por inactividad")

    def _get_model(self):
        with self._model_lock:
            if self.model is None:
                self.model = self.factory(self.model_name)
            return self.model

    def _run(self, path: Path, cancel: threading.Event, family: Optional[str] = None) -> dict:
        started = self.clock()
        audio = decode(path, family=family)
        duration = audio.size / SAMPLE_RATE
        if cancel.is_set():
            raise TraspasoError(504, "la transcripción tardó demasiado")
        model = self._get_model()
        segments, _ = model.transcribe(audio, language="es", beam_size=BEAM_SIZE, vad_filter=True,
                                       condition_on_previous_text=False, temperature=0.0)
        parts = []
        for segment in segments:
            if cancel.is_set():
                raise TraspasoError(504, "la transcripción tardó demasiado")
            parts.append(segment.text.strip())
        text = " ".join(p for p in parts if p).strip()
        return {"texto": text, "duracion": round(duration, 2), "proceso": round(self.clock() - started, 2)}

    def _release(self) -> None:
        self.busy = False

    def _finished(self, future, tmp: Path) -> None:
        tmp.unlink(missing_ok=True)
        if not future.cancelled():
            future.exception()
        if self.model is not None:
            self._schedule_unload()
        self._release()

    async def transcribe(self, stream, content_type: str) -> dict:
        if not self.enabled:
            raise TraspasoError(404, "la voz está deshabilitada")
        if self.busy:
            raise TraspasoError(409, "ya hay una transcripción en curso")
        self.busy = True
        handed_over = False
        part = _Part(self.tmp_dir, limit=MAX_AUDIO, label="el audio supera los 10 MB")
        try:
            self.tmp_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(self.tmp_dir, 0o700)
            try:
                await asyncio.wait_for(read_multipart(stream, content_type, part, MAX_AUDIO + MAX_BODY_OVERHEAD),
                                       UPLOAD_TIMEOUT)
            except asyncio.TimeoutError:
                raise TraspasoError(408, "la subida del audio tardó demasiado")
            except TraspasoError:
                raise
            except Exception:
                raise TraspasoError(400, "pedido multipart inválido")
            if part.tmp is None or part.size == 0:
                raise TraspasoError(400, "falta el audio")
            family = AUDIO_TYPES.get(part.ctype)
            if family is None:
                raise TraspasoError(415, "tipo de audio no permitido")
            with part.tmp.open("rb") as fh:
                head = fh.read(16)
            if sniff(head) != family:
                raise TraspasoError(415, "el contenido no coincide con el tipo del audio")
            cancel = threading.Event()
            task = asyncio.ensure_future(asyncio.to_thread(self._run, part.tmp, cancel, family))
            handed_over = True
            tmp = part.tmp
            task.add_done_callback(lambda fut: self._finished(fut, tmp))
            try:
                result = await asyncio.wait_for(asyncio.shield(task), self.timeout)
            except asyncio.TimeoutError:
                cancel.set()
                raise TraspasoError(504, "la transcripción tardó demasiado")
            except TraspasoError:
                raise
            except Exception as exc:
                log.warning("voz: falló la transcripción (%s)", type(exc).__name__)
                raise TraspasoError(500, "falló la transcripción")
            log.info("voz: %.1f s de audio, %.1f s de proceso", result["duracion"], result["proceso"])
            return result
        finally:
            if not handed_over:
                part.discard()
                self._release()
