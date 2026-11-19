
from fastapi.testclient import TestClient

from conftest import ORIGIN, PIN, make_snapshot, write_transcript
from orquestador.app import create_app
from orquestador.board import BoardHub
from orquestador.config import Config, hash_pin, load_config, save_config
from orquestador.digest import DigestService
from orquestador.enchufe import FakeTerminales
from orquestador.state import StateStore


def test_load_config_ignora_claves_viejas(tmp_path):
    (tmp_path / "config.toml").write_text(
        'pin = ""\n'
        "reenvio_directo = true\n"
        "consulta_autonoma = true\n"
        'clave_que_no_existe = "x"\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    assert isinstance(cfg, Config)


def test_app_arranca_con_config_vieja(tmp_path, handoffs):
    projects = tmp_path / "projects"
    write_transcript(projects)
    data = tmp_path / "data"
    data.mkdir()
    (data / "config.toml").write_text(
        f'pin = "{hash_pin(PIN)}"\n'
        f'claude_projects_dir = "{projects}"\n'
        f'claude_cwd = "{tmp_path}"\n'
        "reenvio_directo = true\n"
        "consulta_autonoma = true\n",
        encoding="utf-8",
    )
    cfg = load_config(data)
    enchufe = FakeTerminales.desde_snapshot(make_snapshot(), poll=0.01)
    digests = DigestService(cfg.projects_dir())
    hub = BoardHub(enchufe, digests)
    hub.self_pane_id = "w2:p9"
    app = create_app(cfg, b"secret", StateStore(data), hub=hub, digests=digests,
                     dist=tmp_path / "nodist", handoffs_dir=handoffs, uploads_dir=tmp_path / "uploads",
                     enchufe=enchufe)
    with TestClient(app, base_url="https://testserver", headers=ORIGIN, client=("127.0.0.1", 5000)) as client:
        assert client.post("/api/login", json={"pin": PIN}).status_code == 200
        assert client.get("/api/board").status_code == 200


CLAVES_VIEJAS = (
    'centinela_vivo = false\n'
    'notas_centinela = "PS9 va en ~/ps9"\n'
    'planes_dir = "~/plans"\n'
    'dios_inactividad_min = 45\n'
    'dios_contexto_max_tokens = 50000\n'
    'dios_timeout_s = 200\n'
)


def test_config_con_todas_las_claves_viejas(tmp_path):
    (tmp_path / "config.toml").write_text('pin = ""\nnombre = "Ana"\n' + CLAVES_VIEJAS, encoding="utf-8")
    cfg = load_config(tmp_path)
    assert cfg.nombre == "Ana"
    for clave in ("centinela_vivo", "notas_centinela", "planes_dir", "dios_inactividad_min",
                  "dios_contexto_max_tokens", "dios_timeout_s"):
        assert not hasattr(cfg, clave), clave
    save_config(cfg, tmp_path)
    guardado = (tmp_path / "config.toml").read_text(encoding="utf-8")
    for linea in CLAVES_VIEJAS.strip().splitlines():
        assert linea in guardado
