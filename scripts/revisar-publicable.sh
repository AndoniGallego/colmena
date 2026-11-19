#!/usr/bin/env bash
# Control antes de armar el ZIP público: arma `git archive HEAD` en un directorio temporal local y busca
# las palabras de una lista propia (una por línea, sin distinguir mayúsculas). Sale con 1 y lista archivo:línea (sin la palabra: la lista es privada)
# si encuentra alguna; con 0 si no hay hallazgos y con 2 si la lista falta o no tiene palabras. Revisa lo commiteado (HEAD), no el árbol de trabajo.
#
#   COLMENA_PALABRAS_PROHIBIDAS  lista de palabras (default ~/.config/colmena/palabras-prohibidas.txt)
#   COLMENA_EXCEPCIONES          regex (una por línea) que debe coincidir con la parte entera del identificador para no contar
#                                (default ~/.config/colmena/palabras-excepciones.txt, opcional)
# El script no trae la lista de palabras: es local y no se versiona.
set -euo pipefail

RAIZ="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
LISTA="${COLMENA_PALABRAS_PROHIBIDAS:-$HOME/.config/colmena/palabras-prohibidas.txt}"
EXCEPCIONES="${COLMENA_EXCEPCIONES:-$HOME/.config/colmena/palabras-excepciones.txt}"

if [[ ! -f "$LISTA" ]]; then
  echo "Falta la lista de palabras: $LISTA (una por línea)" >&2
  exit 2
fi

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
git -C "$RAIZ" archive HEAD | tar -x -C "$TMP"

python3 -I - "$TMP" "$LISTA" "$EXCEPCIONES" <<'PY'
import os
import re
import sys

raiz, lista, excepciones = sys.argv[1:4]

def leer(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return []


palabras = leer(lista)
if not palabras:
    print(f"La lista de palabras está vacía (solo comentarios o líneas en blanco): {lista}", file=sys.stderr)
    sys.exit(2)
exc = [re.compile(e, re.I) for e in leer(excepciones)]
PARTES = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
TOKENS = re.compile(r"\w+")

palabras_min = [p.lower() for p in palabras]
previo = re.compile("|".join(re.escape(p) for p in palabras), re.I)
hallazgos = []


def hay_hallazgo(token):
    """La palabra cuenta si cae entera dentro de una parte del identificador (snake_case/camelCase) que no es
    una palabra genérica entera; si cruza el borde entre dos partes es casualidad y no cuenta."""
    partes = [(m.start(), m.end(), m.group(0)) for m in PARTES.finditer(token)] or [(0, len(token), token)]
    bajo = token.lower()
    for p in palabras_min:
        i = bajo.find(p)
        while i != -1:
            for ini, fin, parte in partes:
                if ini <= i and i + len(p) <= fin:
                    if not any(e.fullmatch(parte) for e in exc):
                        return True
                    break
            i = bajo.find(p, i + 1)
    return False


def revisar(texto, donde):
    if not previo.search(texto):
        return
    for m in TOKENS.finditer(texto):
        if hay_hallazgo(m.group(0)):
            hallazgos.append(donde)


for dirpath, _dirs, files in os.walk(raiz):
    for nombre in files:
        path = os.path.join(dirpath, nombre)
        rel = os.path.relpath(path, raiz)
        revisar(rel, rel + ":0")
        try:
            with open(path, "rb") as fh:
                crudo = fh.read()
        except OSError:
            continue
        if b"\0" in crudo[:4096]:
            continue
        for n, linea in enumerate(crudo.decode("utf-8", "replace").splitlines(), 1):
            revisar(linea, f"{rel}:{n}")

for h in dict.fromkeys(hallazgos):
    print(h)
print(f"{len(hallazgos)} hallazgos", file=sys.stderr)
sys.exit(1 if hallazgos else 0)
PY
