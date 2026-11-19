#!/bin/bash
# Los ejemplos ```pruebas de la regla tienen que respetar el formato que Colmena dibuja.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REGLA="$HERE/../reglas/colmena/informe-pruebas.md"

python3 -I - "$REGLA" <<'EOF'
import json, re, sys

LIM = {"titulo": 100, "resumen": 300, "nombre": 120, "detalle": 400, "evidencia": 500}
RESULTADOS = {"ok", "falla", "omitida"}

try:
    texto = open(sys.argv[1], encoding="utf-8").read()
except OSError as e:
    print(f"FAIL no se puede leer la regla: {e}")
    sys.exit(1)

bloques = re.findall(r"^```pruebas\n(.*?)\n```", texto, re.S | re.M)
fallas = []
if len(bloques) < 2:
    fallas.append(f"se esperaban al menos 2 ejemplos ```pruebas, hay {len(bloques)}")

def largo(campo, valor, donde):
    if not isinstance(valor, str) or not valor.strip():
        fallas.append(f"{donde}: '{campo}' tiene que ser texto no vacío")
    elif len(valor) > LIM[campo]:
        fallas.append(f"{donde}: '{campo}' supera {LIM[campo]} caracteres")

resultados_vistos = set()
evidencias = set()
for i, cuerpo in enumerate(bloques, 1):
    donde = f"ejemplo {i}"
    try:
        data = json.loads(cuerpo)
    except ValueError as e:
        fallas.append(f"{donde}: JSON inválido ({e})")
        continue
    largo("titulo", data.get("titulo"), donde)
    if "resumen" in data:
        largo("resumen", data["resumen"], donde)
    casos = data.get("casos")
    if not isinstance(casos, list) or not 1 <= len(casos) <= 60:
        fallas.append(f"{donde}: 'casos' tiene que tener de 1 a 60 elementos")
        continue
    for j, caso in enumerate(casos, 1):
        d = f"{donde} caso {j}"
        largo("nombre", caso.get("nombre"), d)
        if caso.get("resultado") not in RESULTADOS:
            fallas.append(f"{d}: resultado '{caso.get('resultado')}' no es ok/falla/omitida")
        resultados_vistos.add(caso.get("resultado"))
        if "detalle" in caso:
            largo("detalle", caso["detalle"], d)
        if "evidencia" in caso:
            largo("evidencia", caso["evidencia"], d)
            if not (str(caso["evidencia"]).startswith("/") or re.fullmatch(r"ss_[a-z0-9]{4,40}", str(caso["evidencia"]))):
                fallas.append(f"{d}: la evidencia tiene que ser una ruta absoluta o un ID ss_")
            evidencias.add("id" if str(caso["evidencia"]).startswith("ss_") else "ruta")

if bloques and resultados_vistos != RESULTADOS:
    fallas.append(f"los ejemplos tienen que mostrar los tres resultados; faltan {sorted(RESULTADOS - resultados_vistos)}")

if bloques and evidencias != {"id", "ruta"}:
    fallas.append("los ejemplos tienen que mostrar evidencia con ID ss_ y con ruta")
if "ss_" not in texto.split("## Qué poner")[-1].split("## Formato")[0]:
    fallas.append("'Qué poner' tiene que mencionar el ID ss_ en evidencia")

for f in fallas:
    print(f"FAIL {f}")
if fallas:
    sys.exit(1)
print(f"ok   {len(bloques)} ejemplos ```pruebas válidos")
EOF
