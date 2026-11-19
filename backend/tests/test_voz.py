import asyncio
import io
import math
import os
import stat
import struct
import threading
import wave

import pytest
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN
from orquestador import voz
from orquestador.app import create_app
from orquestador.state import StateStore
from orquestador.traspaso import TraspasoError


def make_wav(seconds=1.0, rate=16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        n = int(seconds * rate)
        w.writeframes(b"".join(struct.pack("<h", int(8000 * math.sin(i / 20))) for i in range(n)))
    return buf.getvalue()


class Seg:
    def __init__(self, text):
        self.text = text


class FakeModel:
    def __init__(self, text=" hola mundo "):
        self.text = text
        self.calls = []
        self.gate = None

    def transcribe(self, audio, **kw):
        self.calls.append((len(audio), kw))
        if self.gate:
            self.gate.wait(5)
        return iter([Seg(self.text)] if self.text else []), None


class Timers:
    def __init__(self):
        self.items = []

    def __call__(self, delay, cb):
        self.items.append((delay, cb))
        return self

    def cancel(self):
        self.items.append(("cancel", None))


@pytest.fixture
def model():
    return FakeModel()


@pytest.fixture
def timers():
    return Timers()


@pytest.fixture
def svc(tmp_path, model, timers):
    return voz.VozService(True, "small", tmp_path, model_factory=lambda name: model, call_later=timers)


@pytest.fixture
def vclient(cfg, tmp_path, handoffs, svc, enchufe):
    app = create_app(cfg, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist",
                     handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", voz=svc, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        assert c.post("/api/login", json={"pin": PIN}).status_code == 200
        yield c


def post(c, data=None, ctype="audio/wav", name="voz.wav", **kw):
    data = make_wav() if data is None else data
    return c.post("/api/voz/transcribir", files={"file": (name, data, ctype)}, **kw)


def leftovers(tmp_path):
    folder = tmp_path / "voz-tmp"
    return [p for p in folder.iterdir()] if folder.exists() else []


def test_transcribe_ok_and_params(vclient, model, tmp_path):
    r = post(vclient)
    assert r.status_code == 200
    body = r.json()
    assert body["texto"] == "hola mundo" and body["duracion"] == pytest.approx(1.0, abs=0.05) and body["proceso"] >= 0
    assert model.calls[0][1]["language"] == "es" and model.calls[0][1]["vad_filter"] is True
    assert r.headers["cache-control"] == "no-store"
    assert leftovers(tmp_path) == []


def test_silence_returns_empty_text(vclient, model):
    model.text = ""
    assert post(vclient).json()["texto"] == ""


def test_requires_session(client):
    assert client.post("/api/voz/transcribir", files={"file": ("v.wav", make_wav(), "audio/wav")}).status_code == 401
    assert client.get("/api/voz/estado").status_code == 401


def test_cross_site_and_bad_origin_rejected(vclient, tmp_path):
    assert post(vclient, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert post(vclient, headers={"Origin": "https://evil.example"}).status_code == 403
    assert vclient.get("/api/voz/estado", headers={"Sec-Fetch-Site": "same-site"}).status_code == 403
    assert leftovers(tmp_path) == []


def test_requires_multipart(vclient):
    r = vclient.post("/api/voz/transcribir", content=b"x" * 10, headers={"Content-Type": "application/json"})
    assert r.status_code == 415


def test_size_limit(vclient, monkeypatch, tmp_path):
    monkeypatch.setattr(voz, "MAX_AUDIO", 1000)
    r = post(vclient, make_wav(0.5))
    assert r.status_code == 413
    assert leftovers(tmp_path) == []


def test_duration_limit_uses_decoded_audio(vclient, monkeypatch, tmp_path, model):
    monkeypatch.setattr(voz, "MAX_SECONDS", 1.0)
    r = post(vclient, make_wav(3.0))
    assert r.status_code == 413 and "segundos" in r.json()["detail"]
    assert model.calls == [] and leftovers(tmp_path) == []


@pytest.mark.parametrize("data,ctype", [
    (b"GIF89a" + b"0" * 32, "audio/webm"), (make_wav(), "audio/webm"), (b"\x1a\x45\xdf\xa3" + b"0" * 32, "audio/wav"),
    (make_wav(), "image/png"), (make_wav(), "application/octet-stream"),
])
def test_magic_and_type_rejected(vclient, data, ctype, tmp_path, model):
    assert post(vclient, data, ctype).status_code == 415
    assert model.calls == [] and leftovers(tmp_path) == []


@pytest.mark.parametrize("head,family", [
    (b"\x1a\x45\xdf\xa3....", "webm"), (b"\x00\x00\x00\x20ftypM4A ", "mp4"), (b"OggS\x00....", "ogg"),
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", "wav"), (b"RIFF\x00\x00\x00\x00WEBPVP8 ", None), (b"", None),
])
def test_sniff(head, family):
    assert voz.sniff(head) == family


def test_undecodable_audio_is_415_and_cleaned(vclient, tmp_path):
    r = post(vclient, b"\x1a\x45\xdf\xa3" + b"\x00" * 64, "audio/webm", "v.webm")
    assert r.status_code == 415 and leftovers(tmp_path) == []


def test_empty_part_and_missing_file(vclient):
    assert post(vclient, b"").status_code == 400
    assert vclient.post("/api/voz/transcribir", data={"a": "b"},
                        files={"x": (None, "y")}).status_code == 400


def test_temp_file_private_while_processing_and_deleted_after(tmp_path, svc, model):
    seen = {}
    original = model.transcribe

    def spy(audio, **kw):
        folder = tmp_path / "voz-tmp"
        files = list(folder.iterdir())
        seen["modes"] = [stat.S_IMODE(os.stat(f).st_mode) for f in files]
        seen["dir"] = stat.S_IMODE(os.stat(folder).st_mode)
        return original(audio, **kw)

    model.transcribe = spy
    body, ctype = multipart(make_wav())
    asyncio.run(svc.transcribe(chunks(body), ctype))
    assert seen["modes"] == [0o600] and seen["dir"] == 0o700
    assert leftovers(tmp_path) == []


def multipart(data, ctype="audio/wav", name="v.wav"):
    boundary = "XXBOUNDARYXX"
    head = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: {ctype}\r\n\r\n").encode()
    return head + data + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


async def chunks(body, size=4096):
    for i in range(0, len(body), size):
        yield body[i:i + size]


def test_temp_deleted_on_model_error(tmp_path, svc, model):
    def boom(audio, **kw):
        raise RuntimeError("secreto del texto")

    model.transcribe = boom
    body, ctype = multipart(make_wav())
    with pytest.raises(TraspasoError) as exc:
        asyncio.run(svc.transcribe(chunks(body), ctype))
    assert exc.value.status == 500 and "secreto" not in exc.value.detail
    assert leftovers(tmp_path) == [] and svc.busy is False


def test_busy_returns_409_and_releases(tmp_path, svc, model):
    model.gate = threading.Event()
    body, ctype = multipart(make_wav())

    async def scenario():
        first = asyncio.ensure_future(svc.transcribe(chunks(body), ctype))
        for _ in range(200):
            if model.calls or svc.busy:
                break
            await asyncio.sleep(0.01)
        with pytest.raises(TraspasoError) as exc:
            await svc.transcribe(chunks(body), ctype)
        assert exc.value.status == 409
        model.gate.set()
        assert (await first)["texto"] == "hola mundo"
        assert svc.busy is False
        return await svc.transcribe(chunks(body), ctype)

    assert asyncio.run(scenario())["texto"] == "hola mundo"
    assert leftovers(tmp_path) == []


def test_timeout_keeps_slot_until_thread_ends_and_cleans(tmp_path, model, timers):
    model.gate = threading.Event()
    svc = voz.VozService(True, "small", tmp_path, model_factory=lambda n: model, call_later=timers, timeout=0.05)
    body, ctype = multipart(make_wav())

    async def scenario():
        with pytest.raises(TraspasoError) as exc:
            await svc.transcribe(chunks(body), ctype)
        assert exc.value.status == 504
        assert svc.busy is True
        with pytest.raises(TraspasoError) as again:
            await svc.transcribe(chunks(body), ctype)
        assert again.value.status == 409
        model.gate.set()
        for _ in range(300):
            if not svc.busy:
                break
            await asyncio.sleep(0.01)
        assert svc.busy is False

    asyncio.run(scenario())
    assert leftovers(tmp_path) == []


def test_disabled_is_404_and_estado_says_so(cfg, tmp_path, handoffs, enchufe):
    svc = voz.VozService(False, "small", tmp_path)
    app = create_app(cfg, b"secret", StateStore(tmp_path), dist=tmp_path / "nodist",
                     handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads", voz=svc, enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as c:
        c.post("/api/login", json={"pin": PIN})
        assert post(c).status_code == 404
        assert c.get("/api/voz/estado").json()["habilitada"] is False


def test_estado_reflects_loaded_model(vclient, timers):
    assert vclient.get("/api/voz/estado").json() == {
        "habilitada": True, "modelo": "small", "cargado": False, "ocupada": False, "max_segundos": 120}
    post(vclient)
    assert vclient.get("/api/voz/estado").json()["cargado"] is True


def test_idle_unload_with_injected_timer(tmp_path, svc, model, timers):
    body, ctype = multipart(make_wav())
    loads = []
    svc.factory = lambda name: (loads.append(name), model)[1]

    async def scenario():
        await svc.transcribe(chunks(body), ctype)
        await asyncio.sleep(0)
        assert svc.model is model
        delay, callback = [t for t in timers.items if t[0] != "cancel"][-1]
        assert delay == voz.IDLE_SECONDS
        callback()
        assert svc.model is None and svc.estado()["cargado"] is False
        await svc.transcribe(chunks(body), ctype)
        assert loads == ["small", "small"]

    asyncio.run(scenario())


def test_idle_unload_postponed_while_busy(svc, model, timers):
    svc.model = model
    svc.busy = True
    svc._unload()
    assert svc.model is model and timers.items[-1][0] == voz.IDLE_SECONDS
    svc.busy = False
    svc._unload()
    assert svc.model is None


def encode(fmt, codec, seconds=1.0):
    import av
    import numpy as np

    buf = io.BytesIO()
    with av.open(buf, "w", format=fmt) as out:
        stream = out.add_stream(codec, rate=48000)
        stream.layout = "mono"
        t = np.arange(int(48000 * seconds)) / 48000
        samples = (np.sin(2 * np.pi * 440 * t) * 0.3).astype("float32").reshape(1, -1)
        frame = av.AudioFrame.from_ndarray(samples, format="fltp", layout="mono")
        frame.sample_rate = 48000
        for packet in stream.encode(frame):
            out.mux(packet)
        for packet in stream.encode(None):
            out.mux(packet)
    return buf.getvalue()


@pytest.mark.parametrize("fmt,codec,ctype,name", [
    ("webm", "libopus", "audio/webm", "v.webm"), ("mp4", "aac", "audio/mp4", "v.m4a"), ("ogg", "libopus", "audio/ogg", "v.ogg"),
])
def test_real_containers_decode(vclient, fmt, codec, ctype, name):
    try:
        data = encode(fmt, codec)
    except Exception as exc:
        pytest.skip(f"PyAV no puede generar {fmt}: {exc}")
    r = post(vclient, data, ctype, name)
    assert r.status_code == 200 and r.json()["duracion"] == pytest.approx(1.0, abs=0.15)


def test_leftovers_swept_on_start(tmp_path):
    folder = tmp_path / "voz-tmp"
    folder.mkdir()
    (folder / ".tmp-old").write_bytes(b"x")
    voz.VozService(True, "small", tmp_path)
    assert list(folder.iterdir()) == []


def test_permissions_policy_allows_mic_on_app(vclient):
    pp = vclient.get("/api/voz/estado").headers["permissions-policy"]
    assert "microphone=(self)" in pp and "camera=()" in pp


def test_no_network(vclient, monkeypatch):
    import socket

    def refuse(*a, **k):
        raise AssertionError("sin red")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    assert post(vclient).status_code == 200


def test_model_missing_is_503(tmp_path, monkeypatch):
    import faster_whisper

    def refuse(*a, **k):
        raise OSError("not found")

    monkeypatch.setattr(faster_whisper, "WhisperModel", refuse)
    with pytest.raises(TraspasoError) as exc:
        voz.load_model("small", tmp_path)
    assert exc.value.status == 503


def test_config_defaults():
    from orquestador.config import Config

    cfg = Config()
    assert cfg.voz_habilitada is True and cfg.voz_modelo == "small"


def test_decode_uses_the_validated_demuxer(tmp_path):
    path = tmp_path / "a.wav"
    path.write_bytes(make_wav(0.5))
    assert voz.decode(path, family="wav").size == pytest.approx(8000, abs=200)
    with pytest.raises(TraspasoError) as exc:
        voz.decode(path, family="ogg")
    assert exc.value.status == 415


def snapshot(tmp_path, files):
    folder = tmp_path / "snap"
    folder.mkdir()
    for name in files:
        (folder / name).write_bytes(b"x")
    return folder


def test_incomplete_model_is_503_without_constructing(tmp_path, monkeypatch):
    import faster_whisper

    def refuse(*a, **k):
        raise AssertionError("no debe construir el modelo: bajaría el tokenizer de internet")

    monkeypatch.setattr(faster_whisper, "WhisperModel", refuse)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    folder = snapshot(tmp_path, ["model.bin", "config.json"])
    with pytest.raises(TraspasoError) as exc:
        voz.load_model(str(folder), tmp_path)
    assert exc.value.status == 503
    assert os.environ["HF_HUB_OFFLINE"] == "1"


def test_model_loads_from_local_path_only(tmp_path, monkeypatch):
    import faster_whisper
    import faster_whisper.utils

    seen = {}

    def fake_fetch(name, **kw):
        seen["fetch"] = kw
        return str(folder)

    def fake_model(path, **kw):
        seen["model"] = (path, kw)
        return "modelo"

    folder = snapshot(tmp_path, voz.MODEL_FILES)
    monkeypatch.setattr(faster_whisper.utils, "download_model", fake_fetch)
    monkeypatch.setattr(faster_whisper, "WhisperModel", fake_model)
    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    assert voz.load_model("small", tmp_path / "models") == "modelo"
    assert seen["fetch"]["local_files_only"] is True
    assert seen["model"][0] == str(folder) and seen["model"][1]["local_files_only"] is True
