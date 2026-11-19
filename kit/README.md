# kit

Kit personal de Claude Code de Ando, dentro de Colmena (antes era el repo andokit). Es independiente de cualquier kit de trabajo que uses en paralelo: no lo toca. Lo instala `uv run orquestador kit instalar`, o el paso "kit" de `uv run orquestador instalar`, que pregunta antes (con Enter no lo instala; `--con-kit` o `--sin-kit` lo deciden sin preguntar).

## Qué hay

| Pieza | Qué es | Se instala como |
|---|---|---|
| `skills/orquestador/` | Skill `/orquestador`: tablero de sesiones recientes y briefs de traspaso que manda Colmena (`recientes.sh` lista sesiones, `digest.sh` resume un transcript) | link en `~/.claude/skills/orquestador` |
| `skills/diagramas/` | Skill `diagramas`: formato del bloque `diagrama` (tipos `estructura`, `secuencia` y `proceso`) con ejemplos; se carga solo al explicar algo | link en `~/.claude/skills/diagramas` |
| `skills/diseno-ui/` | Skill `diseno-ui`: revisar, pulir y animar UI web y gestos táctiles (iPhone y escritorio, Vue 3 con CSS propio); enruta a 4 fuentes MIT fijadas a commit en `fuentes/` (ver `ORIGEN.md`) | link en `~/.claude/skills/diseno-ui` |
| `reglas/colmena/preguntas-con-opciones.md` | Regla global: preguntar en texto, con un bloque `opciones` que la app Orquestador muestra como botones | link en `~/.claude/rules/` (Claude Code la carga en todas las sesiones) |
| `reglas/colmena/diagramas.md` | Regla global corta: al pedir explicar algo, responder con un bloque `diagrama` y cargar antes la skill `diagramas` (que tiene el formato completo) | link en `~/.claude/rules/` (Claude Code la carga en todas las sesiones) |
| `reglas/colmena/colmena-pestanas.md` | Regla global: para abrir pestañas, tarjetas o terminales, pedírselo a Colmena con `[colmena-pestana]` (una pestaña o una tarjeta con hasta 6) | link en `~/.claude/rules/` (Claude Code la carga en todas las sesiones) |
| `ganchos/andokit-sin-askuser.sh` | Hook PreToolUse (AskUserQuestion): niega la herramienta y pide usar un bloque `opciones` en el texto | link en `~/.claude/hooks/`, registrado en `settings.json` |
| `ganchos/andokit-stop-bloques.sh` | Hook Stop: en terminales de Colmena exige el bloque `estado` al cerrar un turno con herramientas y corrige `opciones`/`diagrama` rotos (una sola vez) | link en `~/.claude/hooks/`, registrado en `settings.json` |
| `ganchos/lib-bloques.sh` | Extractor de bloques que cargan los hooks (tiene que estar junto a ellos) | link en `~/.claude/hooks/` |
| `reglas/colmena/informe-pruebas.md` | Regla global: al terminar una ronda de pruebas, declararla en un bloque `pruebas` (casos ok/falla/omitida con evidencia) que la app Orquestador muestra como tarjeta y guarda en la Biblioteca | link en `~/.claude/rules/` (Claude Code la carga en todas las sesiones) |
| `reglas/colmena/comando-sesion.md` | Regla global: cuando la sesión necesita que Ando corra un comando, lo pide en un bloque `comando` (uno por bloque, con motivo, sin secretos) que Colmena muestra con Correr/No y escribe como `!comando` en la misma sesión; lo que la sesión puede hacer sola (p. ej. actualizar un MR) no se pide | link en `~/.claude/rules/` (Claude Code la carga en todas las sesiones) |
| `reglas/colmena/entornos-pc.md` | Regla global: si Ando está en la PC, mandarlo a la ventana Entornos de la app de Windows de Colmena (túnel SSH) en vez de `localhost` de la notebook; manual o fuera de casa, alternativas | link en `~/.claude/rules/` (Claude Code la carga en todas las sesiones) |

La app Colmena tiene una vista **Kit** (menú de la barra superior): muestra si el kit está al día (el mismo chequeo que `kit instalar --check`), un botón **Arreglar** que reinstala, y el catálogo de reglas (se pueden leer enteras), skills y hooks. Cada regla lleva una línea `<!-- propósito: ... -->` después del aviso de la línea 3, que es lo que la vista muestra como resumen (si falta, usa el primer párrafo); las skills usan la `description` del frontmatter y los hooks la primera línea de comentario del script. Endpoints: `GET /api/kit`, `GET /api/kit/regla/<id>`, `POST /api/kit/arreglar`.

Además hay piezas del entorno de trabajo del dueño (un actualizador del kit de trabajo, su wrapper de statusline y una skill de emulador) que no van en la copia pública. Las units que declare `[kit_trabajo].units` en el `config.toml` se copian desde `deploy/` (no se linkean) porque `systemctl enable` se comporta distinto con unit files que son symlinks.

## Dependencias

bash, jq, systemd de usuario, `claude`, `flock`, `notify-send` (opcional), y el kit de trabajo instalado si usás sus piezas opcionales.

## Instalar

Desde la raíz del repo de Colmena:

```bash
uv run orquestador kit instalar --dry-run   # qué haría
uv run orquestador kit instalar             # instala; idempotente
uv run orquestador kit instalar --check     # drift: faltantes, links ajenos o que sobran, units, hooks y statusLine (exit 1 si hay)
uv run orquestador kit desinstalar          # saca los links y los hooks del kit (no toca units, statusLine ni respaldos)
```

Lo que ya existe en el destino y no es nuestro link se mueve a `~/.local/state/andokit/backup/<timestamp>/` antes de reemplazarlo; nunca se borra nada sin respaldo; los links viejos que apuntan al kit o al repo andokit y ya no corresponden se sacan (en `--check` salen como `SOBRA`). El instalador registra los dos hooks en `settings.json` (`PreToolUse` y `Stop`): reemplaza solo los grupos cuyo comando contiene `/andokit-`, deja los demás hooks como están y en el mismo orden, y respalda el archivo en `<state>/backup/<timestamp>/settings/` antes de escribir; si `settings.json` es un symlink, escribe el archivo real. Si el JSON es inválido, o el archivo cambia mientras lo escribe, no lo toca y termina con FAILED. Si una unit cambia, corre `systemctl --user daemon-reload`.

El instalador no habilita ni arranca units; si declaraste alguna en `[kit_trabajo].units`, habilitala a mano con `systemctl --user enable --now <unit>`.

### Statusline

El kit de trabajo puede setear `statusLine` en `~/.claude/settings.json` solo si falta, y pisa su script en `~/.local/bin` en cada update; por eso se envuelve en vez de editarlo. El instalador pone `statusLine.command` en `$HOME/.local/bin/andokit-statusline` solo si `statusLine` falta; si ya hay otro, no lo toca y `--check` lo avisa con `INFO`. `kit desinstalar` deja el link del wrapper si `statusLine` lo usa.

El wrapper escribe `~/.local/state/andokit/ctx/<session_id>.json` (dir 0700, archivo 0600) con `session_id`, `model_id`, `total_input_tokens`, `context_window_size`, `pct` y `ts` (epoch). `pct` es el que muestra el statusline (`tokens * 100 / size`, truncado); `context_window_size` es el denominador efectivo (si Claude Code no lo manda, la misma tabla por modelo). Si falta `total_input_tokens` no se guarda `pct` (el kit lo saca del transcript). Es fail-open: ante cualquier falla se renderiza igual el statusline.

## Configuración propia de la máquina

- `config.local` (gitignored; se lee como texto, nunca se ejecuta): overrides del instalador — `ANDOKIT_BIN_DIR`, `ANDOKIT_SKILLS_DIR`, `ANDOKIT_RULES_DIR` (default `~/.claude/rules`), `ANDOKIT_HOOKS_DIR` (default `~/.claude/hooks`), `ANDOKIT_SETTINGS` (default `~/.claude/settings.json`), `ANDOKIT_SYSTEMD_DIR`, `ANDOKIT_STATE_DIR`, `ANDOKIT_REPO_VIEJO` (default `~/Proyectos/andokit`, para reconocer sus links viejos) y `ANDOKIT_NO_RELOAD=1` (no recarga systemd; lo usan los tests). `ANDOKIT_NO_CONFIG_LOCAL=1` ignora `config.local`.
- Wrapper del statusline: `ANDOKIT_STATUSLINE_TARGET` (default `~/.local/bin/claude-statusline-context.sh`) y `ANDOKIT_STATE_DIR`.
- Actualizador del kit de trabajo (si lo tenés): sus rutas se configuran con variables propias; ver su documentación.
- `skills/orquestador`: no manda nada por su cuenta; el brief lo manda Colmena.

## Mover o compartir

Copiar el repo de Colmena (sin `kit/config.local`), correr `uv run orquestador kit instalar --check` y luego `uv run orquestador kit instalar`. Revisar la sección anterior antes de pasárselo a otra persona.

## No incluido

- `orquestador.service`: pertenece a `~/Proyectos/orquestador/deploy`.
- Todo lo que instala el kit de trabajo, cursor-agent y binarios de terceros.

## Tests

Desde la raíz del repo de Colmena:

```bash
uv run pytest backend/tests/test_kit_bash.py        # corre todos los kit/tests/*.sh
uv run pytest backend/tests/test_kit_instalador.py backend/tests/test_cli_kit.py
```
