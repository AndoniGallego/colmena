#!/bin/bash
# Los ejemplos ```comando de la regla tienen que respetar el formato que Colmena acepta para correrlos.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGLA="$HERE/../reglas/colmena/comando-sesion.md"

python3 -I - "$REGLA" <<'PY'
import json, re, sys, unicodedata

PROHIBIDAS = ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp")
INVISIBLES = set("ᅟᅠㅤﾠ⠀")
SECRETOS = re.compile(r"glpat-|ghp_|xox[bp]-|password=|passwd=|token=|secret=|api[_-]?key=", re.I)

try:
    texto = open(sys.argv[1], encoding="utf-8").read()
except OSError as e:
    print(f"FAIL no se puede leer la regla: {e}")
    sys.exit(1)

bloques = re.findall(r"^```comando\n(.*?)\n```", texto, re.S | re.M)
fallas = []
if len(bloques) < 2:
    fallas.append(f"se esperaban al menos 2 ejemplos ```comando, hay {len(bloques)}")

con_carpeta = False
for i, cuerpo in enumerate(bloques, 1):
    donde = f"ejemplo {i}"
    try:
        data = json.loads(cuerpo)
    except ValueError as e:
        fallas.append(f"{donde}: JSON inválido ({e})")
        continue
    if not isinstance(data, dict):
        fallas.append(f"{donde}: tiene que ser un objeto")
        continue
    extra = set(data) - {"comando", "motivo", "carpeta"}
    if extra:
        fallas.append(f"{donde}: campos desconocidos {sorted(extra)}")
    cmd = data.get("comando")
    if not isinstance(cmd, str) or not 1 <= len(cmd) <= 500:
        fallas.append(f"{donde}: 'comando' tiene que ser texto de 1 a 500 caracteres")
    else:
        malos = [c for c in cmd if unicodedata.category(c) in PROHIBIDAS or c in INVISIBLES
                 or (unicodedata.category(c) == "Zs" and c != " ")]
        if malos:
            fallas.append(f"{donde}: 'comando' tiene caracteres de control o invisibles (una sola línea)")
        if cmd != cmd.strip() or cmd.startswith("-"):
            fallas.append(f"{donde}: 'comando' no puede empezar/terminar con espacios ni empezar con -")
        if SECRETOS.search(cmd):
            fallas.append(f"{donde}: el comando parece llevar un secreto")
    motivo = data.get("motivo")
    if not isinstance(motivo, str) or not motivo.strip() or len(motivo) > 200:
        fallas.append(f"{donde}: 'motivo' tiene que ser texto no vacío de hasta 200 caracteres")
    if "carpeta" in data:
        con_carpeta = True
        if not isinstance(data["carpeta"], str) or not data["carpeta"].startswith("/"):
            fallas.append(f"{donde}: 'carpeta' tiene que ser una ruta absoluta")

if "carpeta actual de tu sesión" not in texto or "inválida" not in texto:
    fallas.append("la regla tiene que decir que 'carpeta' debe ser la carpeta actual de tu sesión o la tarjeta queda inválida")
if bloques and not con_carpeta:
    fallas.append("algún ejemplo tiene que mostrar 'carpeta'")
for frase, motivo in (("secreto", "tiene que prohibir secretos en el comando"),
                      ("un comando por bloque", "tiene que pedir un comando por bloque"),
                      ("MR", "tiene que decir que tareas como actualizar un MR las hace la sesión")):
    if frase.lower() not in texto.lower():
        fallas.append(f"la regla {motivo} (falta '{frase}')")

for f in fallas:
    print(f"FAIL {f}")
if fallas:
    sys.exit(1)
print(f"ok   {len(bloques)} ejemplos ```comando válidos")
PY
