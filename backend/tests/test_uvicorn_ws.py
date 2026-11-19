import uvicorn


def test_uvicorn_auto_ws_protocol():
    config = uvicorn.Config(None, ws="auto")
    config.load()
    assert config.ws_protocol_class is not None


def test_uvicorn_auto_ws_falla_sin_implementacion(monkeypatch):
    import uvicorn.protocols.websockets.auto as auto_mod

    monkeypatch.setattr(auto_mod, "AutoWebSocketsProtocol", None, raising=False)
    config = uvicorn.Config(None, ws="auto")
    config.load()
    assert config.ws_protocol_class is None
