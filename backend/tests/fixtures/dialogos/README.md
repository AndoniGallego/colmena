# Fixtures de diálogos de Claude Code (Fase 0, v1.4)

Capturadas el 2026-11-01 en una sesión de Herdr descartable (`herdr --session pruebas`), con un proyecto temporal en el scratchpad. Nada de esto toca la sesión principal.

- Claude Code **2.1.316**, Herdr **0.9.1** (protocolo 22).
- Claude se lanzó en modo de permisos por defecto: `claude --permission-mode default --settings '{"sandbox":{"enabled":false}}'`.
- El `sandbox` hubo que apagarlo: con el sandbox del usuario activo, los comandos `Bash` se auto-aprueban y no aparece diálogo. En sesiones reales el diálogo de Bash solo sale para comandos fuera del sandbox o sin regla.
- Con `--setting-sources project,local` (sin los hooks de Herdr del usuario) el snapshot **no trae `agent_session`** (`session_id` queda `null`). Con los hooks normales, `agent get` trae `agent_session.value` (el id del `.jsonl`).
- `pane read --source detection --format ansi` devuelve **texto plano igual que `--format text`** (los 38 pares son idénticos). Se guardó solo la versión `.txt`.
- La lectura `detection` trae el final del buffer: arriba puede haber historia de la conversación, y el diálogo va siempre al fondo (con líneas en blanco de relleno). El parser tiene que anclar desde abajo, como dice B3.

## Convención de archivos

`<caso>-<paso>.txt` es la pantalla (`pane read --source detection --lines 60 --format text`). Cada `.txt` tiene un `.json` con `agent_status`, `state_change_seq`, `revision` y `session_id` del momento de la captura. `<caso>-dialog.transcript.json` es la entrada `tool_use` pendiente del transcript. Otros: `bash-2-settings.local.json` (regla guardada), `bash-3-rechazo.tool_result.json` (qué escribe el transcript al rechazar), `trust-0.txt` (diálogo de confianza de carpeta).

Casos: `bash-1` (redirección a archivo, opción 2 "always allow access"), `bash-2` (`git commit`, opción 2 "don't ask again"), `bash-3` (No), `bash-4` (`down` + `enter`), `write-1`, `edit-1`, `edit-2`, `esc-test`, `auq-1` (simple), `auq-2` (otro/"Type something"), `auq-3` y `auq-4` (multiSelect), `auq-5` (dos preguntas), `auq-6` (Esc), `auq-7` ("Chat about this").

## Semántica de teclas (confirmada)

Permisos (Bash, Edit, Write):
- **Un dígito selecciona Y confirma** (no hace falta Enter). `1` = Yes, y se ejecuta.
- `enter` confirma la opción donde está el cursor. `down` solo mueve el cursor (`bash-4-after-down`).
- **Un "No" interrumpe el turno**, igual que `esc`: la pantalla muestra "Interrupted · What should Claude do instead?", el agente pasa a `idle` y el transcript escribe un `tool_result` con `is_error: true` ("User rejected tool use"). La hipótesis de la spec de que "no nunca se manda como esc porque interrumpe" no se sostiene: el No del diálogo también interrumpe, no hay forma de rechazar sin interrumpir.
- **El número del "No" no es fijo**: Bash tiene 4 opciones (No = 4), Edit/Write tienen 3 (No = 3). Hay que sacar el dígito del texto de cada opción, nunca de una tabla fija.
- `esc` = rechazar (mismo efecto que No).
- El diálogo de confianza de carpeta (`trust-0.txt`) no tiene números y **ignora los dígitos**; ahí hay que usar `down`/`enter`. No es un diálogo que la app deba contestar.

AskUserQuestion:
- Una pregunta sin multiSelect: **el dígito selecciona y confirma**. `esc` declina (la pantalla muestra "User declined to answer questions"; Claude sigue y contesta, el agente termina `idle`).
- "Type something.": el dígito (4 con 3 opciones) **solo mueve el cursor y abre el campo**; el texto literal reemplaza la etiqueta (`pane send-text`), y `enter` confirma. Resultado: "User answered ... → Frutilla". Mientras está el campo abierto el pie agrega "ctrl+g to edit in Vim".
- "Chat about this" es la última opción, numerada seguido, **debajo de una línea separadora**. Su dígito declina el cuestionario y Claude pide aclaración. No hay que confundirla con una opción.
- Varias preguntas: el dígito selecciona y **avanza solo a la siguiente pestaña**; la respuesta última lleva a la pantalla de revisión. `left`/`right` navegan entre pestañas; una pregunta ya respondida se ve con `✔` al lado de la opción y el cursor en la 1. En la revisión: "1. Submit answers" / "2. Cancel"; `1` envía y confirma sin Enter; `2` cancela ("User declined to answer questions").
- multiSelect: el **dígito alterna la casilla** `[ ]`/`[✔]` y el cursor **no se mueve**; `space` alterna la del cursor; `down` mueve. Hay una fila "Type something" con casilla y una fila **"Submit" sin número**. `enter` sobre "Submit" o `right` llevan a la pantalla de revisión (también con una sola pregunta), y ahí `1` envía.

## Formato observado frente a la hipótesis de B2 (diferencias)

Permiso de Bash (`bash-1`, `bash-2`):
- Cabecera " Bash command"; opcionalmente una línea "Tip: auto mode handles these prompts for you...". Después viene la `description` del tool_use, una línea de `╌` y el comando entre dos líneas de `╌`. No hay `Push de la rama` debajo del comando, la descripción va **arriba**.
- Hay una línea extra antes de la pregunta cuando aplica: "This command requires approval". La pregunta es "Do you want to proceed?".
- Opciones (hasta **4**, no 3): `1. Yes`, `2. Yes, and don’t ask again for: git commit *` (apóstrofe tipográfico `’`; la regla es el prefijo con `*`, no "git push commands in <dir>"), `3. Yes, and switch to auto mode · auto mode handles these prompts for you`, `4. No`. No aparece "(esc)" ni "tell Claude what to do differently".
- Si el comando redirige a un archivo, la 2 cambia a `Yes, and always allow access to <dir> from this project` (el path se parte en una línea aparte, sangrada, y la opción ocupa 3 líneas). Contestarla con Enter no escribió nada en `settings.local.json` (parece ser solo de sesión; no verificado en otro lado).
- Pie: "Esc to cancel · Tab to amend".
- **Regla guardada**: `Bash(git commit *)` en `<proyecto>/.claude/settings.local.json` (`bash-2-settings.local.json`), clave `permissions.allow`. Después de la regla, `git commit ...` ya no pregunta.

Permiso de Write/Edit (`write-1`, `edit-1`):
- Cabecera " Create file" o " Edit file", el nombre del archivo, el contenido o el diff con números de línea (`2 -dos` / `2 +DOS`) entre líneas `╌`.
- Pregunta "Do you want to create notas.txt?" / "Do you want to make this edit to notas.txt?".
- 3 opciones: `1. Yes`, `2. Yes, and switch to accept edits (auto-approve file edits and common file commands) for this session (shift+tab)`, `3. No`. Con la 2 el modo pasa a "accept edits on" para la sesión y los siguientes edits ya no preguntan.

AskUserQuestion (`auq-*`):
- La barra de pestañas aparece **también con una pregunta**: ` ☐ Color` (simple) o `←  ☐ Lenguajes  ✔ Submit  →` (multiSelect). Con varias: `←  ☐ Editor  ☐ SO  ✔ Submit  →`; las respondidas pasan a `☒`.
- Las opciones van como `1. Rojo` con la descripción sangrada en la línea siguiente. La de texto libre es `Type something.` (con punto en simple, **sin punto y con casilla** en multiSelect). Después hay una línea separadora y `N+1. Chat about this`. La spec no menciona ni la separadora ni "Chat about this".
- El pie es "Enter to select · ↑/↓ to navigate · Esc to cancel" (una pregunta) o "Enter to select · Tab/Arrow keys to navigate · Esc to cancel" (varias).
- El cursor `❯` está en la opción 1 al abrir; en multiSelect el `❯` puede estar sobre "Submit" (sin número).
- La pantalla de revisión dice "Review your answers", lista ` ● <pregunta>` y `   → <respuesta>`, luego "Ready to submit your answers?" y las opciones `1. Submit answers` / `2. Cancel` (la spec decía "Submit answers" / "Cancel": coincide salvo la numeración).

## `blocked` frente al transcript

- `agent_status` pasó a `blocked` en **todos** los casos (Bash, Write, Edit, AskUserQuestion simple/multi/varias).
- El `tool_use` pendiente ya estaba en el `.jsonl` cuando `agent wait --until blocked` volvió, en los 12 casos leídos. Medido 3 veces seguidas con Bash: el `tool_use` lleva marca de tiempo unos 0,35-0,40 s **antes** de que vuelva el wait (03:43:03.804 vs 03:43:04.213, etc.). Es una medida con `timestamp` del mensaje, no del write, pero estaba presente. El riesgo "transcript se escribe después" no apareció.
- `state_change_seq` **no cambió** mientras el agente siguió `blocked` y se movió el cursor, se navegaron pestañas o se alternaron casillas (por ejemplo `auq-5`: 51 durante todo el diálogo). Cambia al salir de `blocked`. No hay ruido observado; la huella con `state_change_seq` es viable.
- El `tool_use` de AskUserQuestion trae `questions[]` estructurado en el `input` (ver `auq-*-dialog.transcript.json`).

## Prueba de cierre de tab

- Tab con `sleep 601` (PID 625137, hijo del bash del pane 624734): `herdr tab close` lo **mató**, junto con el bash. Verificado con `ps`.
- Tab con Claude idle (PID 626467): `herdr tab close` lo **mató**. Verificado con `ps`.
- No se probó cerrar un tab con Claude `working` ni `blocked`.

## Qué cambia para la spec

1. Permiso de Bash: hay hasta 4 opciones y el "No" es la última, no la 3. El parser no puede asumir 3 ni mapear `no` a un dígito fijo.
2. "No" y `esc` interrumpen el turno; no existe un rechazo "limpio" en esta versión. La spec tiene que decir que rechazar interrumpe.
3. El dígito selecciona y confirma en permisos y en preguntas simples; en multiSelect alterna y no confirma; en "Type something" solo abre el campo.
4. Aparecen "Chat about this" y la fila "Submit" sin número, que la spec no contempla; hay que excluirlas de las opciones de respuesta.
5. multiSelect siempre pasa por la pantalla de revisión, también con una pregunta.
6. La regla "don't ask again" para Bash es `Bash(<prefijo> *)` en `.claude/settings.local.json` del proyecto, no un texto con el directorio.
7. Cualquier cambio de versión de Claude Code puede mover todo esto: hacer un test de humo manual contra estas fixtures tras cada `claude update`.

## Efectos colaterales de la captura (para tener en cuenta)

- Aceptar el diálogo de confianza de carpeta hizo que Claude Code escribiera el proyecto temporal en `~/.claude.json`, y los transcripts quedaron en `~/.claude/projects/-tmp-claude-1000--home-usuario-proyectos-acme-...-scratchpad-fase0-proj/`. No se borró nada ahí.
- La regla `Bash(git commit *)` se guardó en el `.claude/settings.local.json` del proyecto temporal, dentro del scratchpad, no en la configuración del usuario.
- Quedó un directorio de sesión detenido `~/.config/herdr/sessions/pruebas` (solo el log del servidor).
