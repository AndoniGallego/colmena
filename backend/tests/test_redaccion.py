import pytest

from orquestador import terminales
from orquestador.redaccion import OCULTO, parece_env, redactar, redactar_basico

POSITIVOS = [
    ("password=hunter2xx", "hunter2xx"),
    ("DB_PASSWORD=supersecreta", "supersecreta"),
    ("STRIPE_KEY = 'abc def ghi'", "abc def ghi"),
    ('"apiKey": "abcdefgh12345"', "abcdefgh12345"),
    ("token: a1b2c3d4e5f6", "a1b2c3d4e5f6"),
    ("Authorization: Bearer abcdef.ghijk", "abcdef.ghijk"),
    ("curl https://user:pa55word@host/x", "pa55word"),
    ("AKIAABCDEFGHIJKLMNOP", "AKIAABCDEFGHIJKLMNOP"),
    ("ghp_abcdefghij123", "ghp_abcdefghij123"),
    ("github_pat_11ABCDEF", "github_pat_11ABCDEF"),
    ("glpat-xyzxyzxyz", "glpat-xyzxyzxyz"),
    ("sk-ant-abcdefghijkl", "sk-ant-abcdefghijkl"),
    ("xoxb-123-456", "xoxb-123-456"),
    ("mysql -u root -pS3cret db", "S3cret"),
    ("mysql -u root -p'con espacio' db", "con espacio"),
    ('psql -p"otra clave"', "otra clave"),
    ("sshpass -p hunter22 ssh x", "hunter22"),
    ("curl --password hunter2secret x", "hunter2secret"),
    ('curl --password "a b" x', "a b"),
    ("curl --password 'a b' x", "a b"),
    ("curl --password=secreto x", "secreto"),
    ("curl -u admin:hunter22 https://x", "hunter22"),
    ("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkw.abcdefghijklmnop", "eyJzdWIiOiIxMjM0NTY3ODkw"),
    ("-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA\n-----END RSA PRIVATE KEY-----", "MIIEpAIBAAKCAQEA"),
    ("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXk", "b3BlbnNzaC1rZXk"),
    ("aws_secret_access_key = wJalrXUtnFEMI/K7MDENG", "wJalrXUtnFEMI/K7MDENG"),
    ("secret_hash: " + "ab12" * 12, "ab12" * 12),
]

NEGATIVOS = [
    "el token de diseño del botón",
    "token: lo genera el backend",
    "la password se resetea desde el panel",
    "secret santa del equipo",
    "usá auth: el SSO de siempre",
    "PS9-71 quedó cerrado con mooauthsso 2.0",
    "ps -p 1234",
]


@pytest.mark.parametrize("texto,secreto", POSITIVOS)
def test_tapa_secretos(texto, secreto):
    out = redactar(texto)
    assert secreto not in out
    assert OCULTO in out


@pytest.mark.parametrize("texto", NEGATIVOS)
def test_no_tapa_prosa(texto):
    assert redactar(texto) == texto


def test_terminales_usa_la_redaccion_basica_sin_cambios():
    assert terminales.redactar is redactar_basico
    assert redactar_basico("token de diseño") == f"token {OCULTO} diseño"


def test_parece_env():
    assert parece_env("API_URL=x\nDB_HOST=y\nDB_PASS=z\n")
    assert not parece_env("API_URL=x\nhola\n")
