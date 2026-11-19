#!/bin/bash
# La skill diseno-ui: entrada propia, fuentes intactas con licencia y procedencia fijada, sin nada ejecutable.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$HERE/../skills/diseno-ui"

python3 -I - "$SKILL_DIR" <<'EOF'
import os, re, sys

base = sys.argv[1]
fuentes = os.path.join(base, "fuentes")
fallas = []

def leer(ruta):
    try:
        return open(ruta, encoding="utf-8").read()
    except OSError as e:
        fallas.append(f"no se puede leer {os.path.relpath(ruta, base)}: {e}")
        return ""

skill = leer(os.path.join(base, "SKILL.md"))
m = re.match(r"---\n(.*?)\n---\n", skill, re.S)
if not m:
    fallas.append("SKILL.md sin frontmatter")
else:
    fm = m.group(1)
    if not re.search(r"^name: diseno-ui$", fm, re.M):
        fallas.append("SKILL.md: falta 'name: diseno-ui'")
    d = re.search(r"^description: (.+)$", fm, re.M)
    if not d or len(d.group(1).strip()) < 40:
        fallas.append("SKILL.md: falta una description útil")

# La adaptación al iPhone y a Vue está en la entrada.
for clave in ("safe-area-inset", "(hover: hover)", "dvh", "<Transition", "touch-action"):
    if clave not in skill:
        fallas.append(f"SKILL.md no menciona {clave}")

# Cada archivo de fuentes que la entrada nombra existe.
for ref in sorted(set(re.findall(r"fuentes/[\w./-]+\.md", skill))):
    if not os.path.isfile(os.path.join(base, ref)):
        fallas.append(f"SKILL.md apunta a {ref}, que no existe")

origen = leer(os.path.join(base, "ORIGEN.md"))
dirs = sorted(d for d in os.listdir(fuentes) if os.path.isdir(os.path.join(fuentes, d))) if os.path.isdir(fuentes) else []
if len(dirs) != 4:
    fallas.append(f"se esperaban 4 fuentes, hay {len(dirs)}")
for d in dirs:
    lic = leer(os.path.join(fuentes, d, "LICENSE"))
    if not lic.startswith("MIT License"):
        fallas.append(f"fuentes/{d}: LICENSE ausente o no MIT")
    if f"fuentes/{d}" not in origen:
        fallas.append(f"ORIGEN.md no documenta fuentes/{d}")
    if f"fuentes/{d}" not in skill:
        fallas.append(f"SKILL.md no dice cuándo leer fuentes/{d}")
if len(set(re.findall(r"\b[0-9a-f]{40}\b", origen))) < 3:
    fallas.append("ORIGEN.md: faltan los 3 commits fijados (sha de 40)")

# Ningún SKILL.md anidado (se cargaría como skill suelta) ni nada ejecutable.
for raiz, _, archivos in os.walk(base):
    for a in archivos:
        ruta = os.path.join(raiz, a)
        rel = os.path.relpath(ruta, base)
        if a == "SKILL.md" and raiz != base:
            fallas.append(f"{rel}: SKILL.md anidado")
        if not (a.endswith(".md") or a == "LICENSE"):
            fallas.append(f"{rel}: solo se admiten .md y LICENSE")
        if os.access(ruta, os.X_OK):
            fallas.append(f"{rel}: es ejecutable")

if fallas:
    for f in fallas:
        print(f"FAIL {f}")
    sys.exit(1)
print("OK skill diseno-ui")
EOF
