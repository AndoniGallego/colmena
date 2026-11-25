#!/bin/bash
# Tests de scripts/armar-instalador.sh sin red ni compilación: COLMENA_ARMAR_CMD reemplaza el armado de Tauri
# por un falso que deja un .exe y un .sig sintéticos. Nunca escriben en data/ del repo: la salida va a un mktemp.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../../scripts/armar-instalador.sh"
T="$(mktemp -d)"
trap 'rm -rf "$T"' EXIT

FAIL=0
check() { if [ "$2" = "$3" ]; then echo "ok   $1"; else echo "FAIL $1: esperado '$3', obtuve '$2'"; FAIL=1; fi; }

: > "$T/clave"
chmod 600 "$T/clave"
cat > "$T/armar-falso" <<'EOF'
#!/bin/bash
# $1 = carpeta de la app, $2 = versión, $3 = carpeta donde Tauri deja el instalador
[ -f "$1/src-tauri/tauri.conf.json" ] || exit 3
[ -n "${FALLAR:-}" ] && exit 1
mkdir -p "$3"
printf 'MZ-%s' "$2" > "$3/Colmena_$2_x64-setup.exe"
printf 'firma-de-%s' "$2" > "$3/Colmena_$2_x64-setup.exe.sig"
EOF
chmod +x "$T/armar-falso"

export COLMENA_TARGET_DIR="$T/target" COLMENA_CLAVE_ACTUALIZADOR="$T/clave" COLMENA_ARMAR_CMD="$T/armar-falso" COLMENA_HERRAMIENTAS="bash"
O="$T/salida"
armar() { COLMENA_AHORA="$1" bash "$SCRIPT" "$O" >"$T/out" 2>"$T/err"; echo $?; }
campo() { python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[sys.argv[2]])' "$O/ultima.json" "$1"; }

# 1. arma, versión desde la hora y ficha válida
check "primera: exit 0" "$(armar 202611251430)" "0"
check "versión 0.AAAAMMDD.HHMM" "$(campo version)" "0.20261125.1430"
check "archivo nombrado" "$(campo archivo)" "Colmena_0.20261125.1430_x64-setup.exe"
check "firma = contenido del .sig" "$(campo firma)" "firma-de-0.20261125.1430"
check "fecha con zona" "$(campo fecha | grep -cE '^2026-11-25T14:30:00[+-][0-9]{2}:[0-9]{2}$')" "1"
[ -n "$(campo notas)" ] && r=si || r=no
check "notas no vacías" "$r" "si"
check "instalador copiado" "$(cat "$O/Colmena_0.20261125.1430_x64-setup.exe")" "MZ-0.20261125.1430"
check "sin temporales" "$(find "$O" -name '*.tmp*' | wc -l)" "0"

# 2. hora con cero adelante: entero (semver no acepta ceros a la izquierda)
check "madrugada: exit 0" "$(armar 202611260905)" "0"
check "0905 -> 905" "$(campo version)" "0.20261126.905"
check "00:05: exit 0" "$(armar 202611270005)" "0"
check "00:05 -> 5" "$(campo version)" "0.20261127.5"

# 3. guarda la última y la anterior; borra las más viejas
check "quedan dos instaladores" "$(ls "$O"/*.exe | xargs -n1 basename | sort | tr '\n' ' ')" \
  "Colmena_0.20261126.905_x64-setup.exe Colmena_0.20261127.5_x64-setup.exe "
check "anterior.json apunta a la anterior" \
  "$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["version"])' "$O/anterior.json")" "0.20261126.905"

# 4. si el armado falla, la ficha anterior queda intacta
antes="$(cat "$O/ultima.json")"
check "armado roto: exit != 0" "$(FALLAR=1 armar 202611281200 | grep -vc '^0$')" "1"
check "ficha intacta" "$(cat "$O/ultima.json")" "$antes"
check "sin instalador nuevo" "$(ls "$O" | grep -c 20261128)" "0"

# 5. sin clave: explica cómo generarla y no arma nada
rm -rf "$O"
check "sin clave: exit 1" "$(COLMENA_CLAVE_ACTUALIZADOR="$T/no-existe" armar 202611251430)" "1"
grep -q 'tauri signer generate' "$T/err" && r=si || r=no
check "sin clave: dice cómo generarla" "$r" "si"
[ -e "$O/ultima.json" ] && r=si || r=no
check "sin clave: no hay ficha" "$r" "no"

# 6. falta una herramienta: la nombra y corta
check "sin herramienta: exit 1" "$(COLMENA_HERRAMIENTAS="bash herramienta-que-no-existe-xyz" armar 202611251430)" "1"
grep -q 'herramienta-que-no-existe-xyz' "$T/err" && r=si || r=no
check "sin herramienta: la nombra" "$r" "si"

# 7. carpeta de salida por variable cuando no hay argumento
O2="$T/por-variable"
COLMENA_AHORA=202611251430 COLMENA_ACTUALIZACIONES_DIR="$O2" bash "$SCRIPT" >/dev/null 2>&1
[ -f "$O2/ultima.json" ] && r=si || r=no
check "salida por COLMENA_ACTUALIZACIONES_DIR" "$r" "si"

# 8. la clave privada nunca aparece en la salida ni en la carpeta publicada
printf 'SECRETO-DE-PRUEBA\n' > "$T/clave"
rm -rf "$O"
armar 202611251430 >/dev/null
grep -rq 'SECRETO-DE-PRUEBA' "$O" "$T/out" "$T/err" && r=si || r=no
check "la clave no se filtra" "$r" "no"

exit "$FAIL"
