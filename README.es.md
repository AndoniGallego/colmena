[English](README.md) · Español

# Colmena

Colmena es un ADE (Agentic Development Environment: un entorno de desarrollo donde el trabajo lo hacen agentes y vos los dirigís). Corre en tu propia máquina Linux. Desde un solo lugar, en la compu o en el celu, lanzás y manejás agentes (sesiones de Claude Code y trabajadores de Cursor), les das trabajo desde tickets, MRs, diffs y tareas programadas, revisás lo que hacen y aprobás lo que piden.

Nada queda expuesto a internet: se entra por Tailscale y con PIN.

## Qué trae

### Agentes

- **Sesiones de Claude Code:** las lanzás, las retomás y las seguís desde el tablero, cada una con su estado y el porcentaje de contexto usado.
- **Trabajadores de Cursor:** una sesión puede delegar un cambio mecánico a `cursor-agent`, en una copia aparte del repo. Vos aprobás cada pedido y tienen topes (2 a la vez, 6 por hora, 45 minutos). Ver [Trabajador Cursor](#trabajador-cursor).
- **Tareas programadas:** pedidos que corren solos a una hora, en un repo, con Claude o con Cursor. Todo viene apagado hasta que lo prendés. Ver [Tareas programadas](#tareas-programadas).
- **Traspasos y pedidos entre sesiones:** pasás contexto de una sesión a otra, y una sesión puede pedir abrir otra pestaña o cerrar una terminal; vos aprobás con un toque.

### Darles trabajo

- **Nueva tarea desde un ticket:** das la clave de Jira (por ejemplo `ABC-123`) y Colmena crea una copia del repo (worktree) en su propia rama y abre una sesión con el pedido de arrancar ese ticket. Ver [Nueva tarea y tickets](#nueva-tarea-y-tickets).
- **Comentar el diff:** marcás líneas en los cambios de una sesión, escribís qué corregir y se los mandás a esa sesión en un solo mensaje. Ver [Comentarios del diff](#comentarios-del-diff).
- **MRs a la sesión:** mandás un job fallido o un hilo de comentarios de un MR a una sesión abierta. Ver [MRs a la sesión](#mrs-a-la-sesión).

### Supervisar y aprobar

- **Tablero de sesiones:** todas las sesiones en vivo. Acomodás las tarjetas y las pestañas como quieras; el orden se guarda y se ve igual en la compu y en el celu.
- **Preguntas y permisos:** contestás lo que te preguntan y aprobás o rechazás permisos sin abrir la terminal.
- **Avisos y notch:** te avisa al celu, en la campana (que guarda el historial) y en el notch de la app de Windows cuando una sesión pregunta, espera una aprobación o termina.
- **Uso del plan de Claude:** la barra muestra cuánto llevás gastado de los límites de 5 horas y de 7 días. Ver [Uso del plan de Claude](#uso-del-plan-de-claude).
- **Terminales en vivo:** ves las terminales de cada pestaña, cerrás las que ya no usás y, si lo prendés, escribís en ellas con confirmación.

### Contexto y memoria

- **Biblioteca:** lo que generan las sesiones (páginas HTML, archivos, diagramas) en un solo lugar.
- **Memoria:** índice local de tus sesiones de los últimos 30 días, con búsqueda desde Ajustes > Memoria (y Engram, si lo tenés).
- **Retomar sesiones viejas:** el botón del reloj busca una sesión de los últimos 30 días y la abre de nuevo en la tarjeta que elijas o en una nueva.
- **Limpieza de sesiones viejas:** propone cerrar las que están quietas; nunca cierra nada sin que lo confirmes.

### Herramientas

- **Dictado por voz:** hablás y el texto queda en el chat, transcripto en tu propia máquina.
- **MRs de GitLab (opcional):** los merge requests de GitLab, solo si lo configurás.
- **Kit para Claude (opcional):** reglas, skills y hooks para las sesiones, con una vista Kit que muestra si está al día y lo arregla con un botón.
- **App de Windows (opcional):** un notch arriba de la pantalla con el estado de las sesiones, donde contestás avisos y preguntas, y una ventana Entornos para abrir las tiendas Docker de la notebook por un túnel SSH.
- **Exportar para compartir:** arma una copia limpia del proyecto, sin tus datos. Ver [Compartir Colmena](#compartir-colmena).

## Requisitos

- Linux con **systemd de usuario** (el instalador arma servicios con `systemctl --user`).
- **Python 3.10 o más** y **[uv](https://docs.astral.sh/uv/)** en el `PATH`.
- **Node 20 o más** y **npm** (el frontend es Vue 3 con Vite).
- **[Claude Code](https://docs.anthropic.com/en/docs/claude-code)** (`claude` en el `PATH`), en la misma máquina.
- Para entrar desde el celu u otra compu: [Tailscale](#entrar-desde-el-celu-u-otra-compu-tailscale).

Si falta algo, `./instalar.sh` te dice qué instalar.

## Instalar en 3 pasos

1. Desde la carpeta de Colmena:

   ```bash
   ./instalar.sh
   ```

   Te pregunta tu nombre, un PIN (8 caracteres o más), en qué carpetas trabajás y si lo vas a usar desde el celu. Arma la app, guarda la configuración en `data/config.toml`, instala los avisos de Claude (si decís que sí) y deja corriendo los servicios `colmena-guardian` y `orquestador`.

2. Para que los servicios sigan al cerrar sesión (una vez por usuario):

   ```bash
   loginctl enable-linger "$USER"
   ```

3. Abrí en el navegador la dirección que te muestra el instalador al final.

Opciones:

- `./instalar.sh --ensayo` muestra qué haría, sin tocar nada.
- `./instalar.sh --sin-servicios` deja las units en `data/units/` y te explica cómo prenderlas a mano.
- El instalador pregunta si instalar el andokit (las reglas, skills y hooks para Claude que usa el autor, en `kit/`); con Enter no lo instala. `--con-kit` o `--sin-kit` lo deciden sin preguntar.
- Se puede volver a correr para actualizar: Enter conserva lo que ya estaba (el PIN no se toca salvo que pidas cambiarlo).

Si querés entrar desde el celu, seguí con la sección siguiente: el instalador te muestra los comandos de `tailscale serve`, pero no los corre.

## Entrar desde el celu u otra compu (Tailscale)

Colmena escucha siempre en `127.0.0.1` y nunca abre un puerto a la red. [Tailscale](https://tailscale.com) es una red privada entre tus dispositivos: solo ellos llegan. Colmena nunca ejecuta `tailscale` por su cuenta; los comandos los corrés vos.

1. **Instalá Tailscale** en la compu donde corre Colmena y en el celu (o la otra compu), con la **misma cuenta**. En Linux: `curl -fsSL https://tailscale.com/install.sh | sh` y después `sudo tailscale up`. En el celu, la app de Tailscale de la tienda.
2. **Activá HTTPS en tu tailnet** (una sola vez, antes de `tailscale serve`): en el [panel de administración](https://login.tailscale.com/admin/dns), sección DNS, prendé *MagicDNS* y *Enable HTTPS certificates*. Sin eso no hay direcciones `https://<tu-maquina>.<tu-red>.ts.net`, y hacen falta para la cookie segura, la app instalable y los avisos.
3. **Publicá Colmena dentro de tu red** (solo la ven tus dispositivos):

   ```bash
   tailscale serve --bg --https=8444 http://127.0.0.1:8770
   tailscale serve --bg --https=8445 http://127.0.0.1:8771   # visor de la Biblioteca
   tailscale serve status                                     # muestra las dos direcciones https
   ```

4. **Configurá Colmena:**
   - En `~/.config/orquestador/orquestador.env` poné `ORQ_APP_ORIGIN` y `ORQ_VIEWER_ORIGIN` con las direcciones que mostró `tailscale serve status` (puertos 8444 y 8445).
   - En `data/config.toml` poné `tailscale_user` con tu login de Tailscale (el mail con el que entraste): así solo entrás vos aunque haya más gente en la red.
   - `[entrada]` puede quedar sin poner (el default es `["tailscale"]`) o `modos = ["tailscale", "solo-local"]` si querés las dos.
5. **Reiniciá Colmena** (`systemctl --user restart orquestador`) y abrí en el celu `https://<tu-maquina>.<tu-red>.ts.net:8444`. Instalala como app (iPhone: Compartir, "Agregar a inicio"; Android: menú, "Instalar app") y aceptá las notificaciones si las querés.

Importante:

- **Nunca uses `tailscale funnel`**: eso sí publica Colmena en internet.
- **Configurá `tailscale_user`.** Con eso, el servidor exige el header `Tailscale-User-Login` y solo entra esa cuenta. Si lo dejás vacío, el chequeo no se aplica.
- **Dejá `cabecera_ip` vacío hasta verificar** qué header manda `tailscale serve` con la IP real del cliente (por ejemplo mirando qué llega en una petición de prueba). Si ponés un header incorrecto, un cliente puede fingir su IP.
- **Bloqueo del PIN.** Mientras `cabecera_ip` no esté configurada, todas las peticiones parecen venir de la propia máquina: los intentos fallidos de PIN se cuentan en conjunto, y varios errores desde un dispositivo bloquean a todos un rato. Cuando verifiques el header, configurala para tener bloqueo por dispositivo.
- Un `curl` directo a `127.0.0.1:8770` da 403 a propósito: falta el aviso de quién sos, que solo agrega `tailscale serve`. Para usar Colmena en la misma compu sin Tailscale, usá el modo `solo-local` (ver la referencia).
- Si cambiás el nombre de la máquina o de la red de Tailscale, cambian las direcciones: actualizá `ORQ_APP_ORIGIN` y `ORQ_VIEWER_ORIGIN` y volvé a iniciar sesión en la app.
- Entrá siempre por la dirección de `ORQ_APP_ORIGIN`: la cookie de sesión y el visor de la Biblioteca solo funcionan con ese origen.

Desde Windows podés hacer lo mismo con Edge o Chrome (instalala como app), o usar la app de Windows de la sección siguiente.

## App de Windows (opcional)

En `windows/colmena-app/` hay una app para Windows hecha con Tauri. No hace falta para usar Colmena: es un extra.

- **Notch:** una pastilla arriba al centro de la pantalla. Cada celda del panal es una sesión pintada según su estado. Al hacer clic se despliega: ves las sesiones, contestás preguntas (con opciones o texto libre), aprobás permisos y el pedido de pestaña con Abrir o No. Los avisos salen del notch en lugar del aviso del navegador.
- **Entornos:** una ventana que lista los entornos Docker que corren en la notebook y los abre con un botón. La app arma un túnel SSH con sus puertos y abre la página en el navegador de la PC. Solo funciona desde la app de Windows; en el navegador la vista es de solo lectura.
- Se maneja desde la bandeja (mostrar u ocultar, abrir Colmena, Entornos, monitor del notch, dirección de la notebook, arrancar con Windows).

La primera vez te pide la dirección HTTPS de Colmena (la de `ORQ_APP_ORIGIN`). Cómo armar el instalador, paso a paso: [`windows/colmena-app/COMPILAR.md`](windows/colmena-app/COMPILAR.md).

## Funciones opcionales del kit de trabajo

Nada de esto es obligatorio para usar el tablero y las terminales. Si no lo configurás, la función queda apagada o la pantalla la muestra deshabilitada.

| Función | Qué hace falta | Si no está |
|---|---|---|
| **MRs de GitLab** | Sección `[mrs]` en `data/config.toml` (`usuario`, `usuario_id`, `equipo`, `repos`, ...) y **`glab`** autenticado contra gitlab.com. | La sección MRs responde 503 ("Los MRs no están configurados"). |
| **Memoria Engram** | Contenedor Docker con Engram (el nombre va en `[engram].contenedor`), `memoria_habilitada` en la config y `docker` en el `PATH`. | El índice local de transcripts sigue; la búsqueda en Engram falla y Ajustes > Memoria lo marca caído. Con `memoria_habilitada = false`, se apaga el índice y la búsqueda de memoria. |
| **Indicador VPN en la statusline** | Variables `<PREFIJO>_VPN_*` (`_VPN_STATUSLINE_ENABLED`, `_VPN_INTERFACE`, `_VPN_SYSFS_DIR`) en la unit o el entorno del orquestador; el prefijo es `COLMENA` salvo que `[kit_trabajo].prefijo_vars` diga otro (`<PREFIJO>_CTX_WARN_PCT` ajusta el aviso de contexto). | No se muestra el ícono de VPN en la statusline. |
| **Herdr** | Binario `herdr`, unit opcional `deploy/herdr-server.service` y `terminales.backends` que lo incluya. | Colmena usa solo `colmena-guardian` para las terminales nuevas (lo que deja el instalador). |

### Nombres de tu kit de trabajo

Colmena no trae nombres de ningún kit externo. Si usás uno, sus nombres propios van en la tabla `[kit_trabajo]` del `data/config.toml` (ejemplo genérico en [`deploy/kit_trabajo.example.toml`](deploy/kit_trabajo.example.toml)); sin ella rigen los valores genéricos:

| Clave | Para qué | Genérico |
|---|---|---|
| `prefijo_vars` | Prefijo de las variables de la statusline (`<PREFIJO>_CTX_WARN_PCT`, `<PREFIJO>_VPN_*`) | `COLMENA` |
| `carpeta_titulos` | Carpeta bajo `~/.claude` con el ticket y título de cada sesión | `.kit-session-title` |
| `script_flujo_git` | Script bajo `~/.local/bin` que dice la rama destino de un MR | `git-flow.sh` |
| `comando_flujo`, `agente_tickets` | Lo que se le pide a la sesión de un ticket | `/flujo-tickets`, `analista de tickets` |
| `apoyo_entornos` | Servicios Docker extra que se tratan como apoyo (no como entorno principal) | `[]` |
| `units` | Units de `deploy/` que instala `kit instalar` | `[]` |

---

# Referencia

Para quien quiera el detalle. Todo lo de configuración va en `data/config.toml`, salvo que se diga otra cosa.

## Instalación a mano

1. Creá `~/.config/orquestador/orquestador.env` a partir de `deploy/orquestador.env.example` y completá `ORQ_APP_ORIGIN`, `ORQ_VIEWER_ORIGIN` y `ORQ_VAPID_SUB` **antes** de instalar o reiniciar la unit. Una línea `ORQ_*=` vacía no pisa el valor de `config.toml` ni el default. Los orígenes son las direcciones HTTPS que muestra `tailscale serve status` (8444 y 8445); `ORQ_VAPID_SUB` suele ser un `mailto:` de contacto.
2. Copiá la unit y recargá systemd:

   ```bash
   mkdir -p ~/.config/systemd/user ~/.config/orquestador
   cp deploy/orquestador.env.example ~/.config/orquestador/orquestador.env
   # editá orquestador.env y completá las variables
   chmod 600 ~/.config/orquestador/orquestador.env
   cp deploy/orquestador.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now orquestador
   journalctl --user -u orquestador -f
   ```

3. Guardián de terminales (corre las sesiones cuando no hay Herdr):

   ```bash
   cp deploy/colmena-guardian.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable --now colmena-guardian
   ```

4. Solo si usás Herdr y querés que arranque solo al bootear (restaura workspaces y retoma cada Claude en su conversación), con linger activo:

   ```bash
   cp deploy/herdr-server.service ~/.config/systemd/user/
   systemctl --user daemon-reload
   systemctl --user enable herdr-server   # sin --now si ya hay un `herdr server` corriendo a mano
   ```

Las units de `deploy/` asumen el repo en `~/Proyectos/orquestador` y `uv` en `~/.local/bin`: si no es tu caso, ajustá `WorkingDirectory`, `ExecStart` y `PATH` (el instalador lo hace solo). La unit exige `EnvironmentFile=`: sin `orquestador.env` el servicio no arranca.

Sin servicios: `uv run orquestador set-pin` y `uv run orquestador`. `ORQ_DATA_DIR` cambia la carpeta de datos. Tras actualizar el kit de trabajo, `uv run orquestador recargar-sesiones` pide al guardián recargar las sesiones de Claude.

El kit personal de Claude (reglas, skills y hooks) vive en `kit/` y lo instala `uv run orquestador kit instalar` (también lo ofrece `orquestador instalar`); detalle en `kit/README.md`.

## Entrada y modos

`[entrada]` define cómo llega el tráfico. `modos` es una lista (default `["tailscale"]`); se pueden combinar.

```toml
[entrada]
modos = ["tailscale", "solo-local"]

[entrada.tailscale]
cabecera_ip = ""            # vacío hasta verificar el header del proxy; luego, por ejemplo "X-Forwarded-For"

[entrada.solo-local]
puerto_app = 8774
origen_app = "http://localhost:8774"
```

| Modo | Escucha en | Quién llega | Qué exige además del PIN |
|---|---|---|---|
| `solo-local` | 8774 | el navegador de la misma compu | `Host` `localhost` o `127.0.0.1` |
| `tailscale` (default) | 8770 app, 8771 visor | `tailscale serve` | `Host` del ts.net y `Tailscale-User-Login` igual a `tailscale_user` |

- **Solo desde tu compu:** `modos = ["solo-local"]`, reiniciá y abrí `http://localhost:8774`. Desde Chrome o Edge se puede instalar como app. El celu no llega.
- En todos los modos: cookie `__Host-orq_session` (Secure, HttpOnly, SameSite=Strict, sin `Domain`), CSRF por `Origin`/`Sec-Fetch-Site` contra el origen del modo, y un `Host` ajeno da 400 (protege de DNS rebinding).
- Los clientes que hablan directo al puerto 8770 sin pasar por `tailscale serve` reciben 403 si hay `tailscale_user`: usá `solo-local` o entrá por HTTPS de Tailscale.
- La Biblioteca se reindexa al arrancar, con cada cambio del tablero y al abrirla (con límite de 60 s), nunca por timer. El PDF se abre en pestaña nueva.

## Guardián y Herdr

Colmena maneja las terminales por dos caminos: el guardián propio (`colmena-guardian`, socket en `$XDG_RUNTIME_DIR/colmena-guardian/guardian.sock`) y Herdr, que es opcional.

```toml
[terminales]
backends = ["herdr", "guardian"]   # qué caminos usar; sin "herdr", Colmena no lo toca
nuevas_en = "guardian"             # dónde se abren los espacios nuevos: "herdr" o "guardian"

[guardian]
# socket = "/ruta/al/guardian.sock"   # solo si no usás el de XDG_RUNTIME_DIR
```

- Sin binario `herdr` (ni en `herdr_bin` ni en el `PATH`), o con `backends` sin `"herdr"`, Colmena arranca solo con el guardián; el log lo dice al arrancar.
- Con Herdr instalado y `backends = ["herdr"]`, todo sigue como antes; sumando `"guardian"` conviven las dos.
- Volver atrás: `backends = ["herdr", "guardian"]` y `nuevas_en = "herdr"`.

## Biblioteca

Muestra lo que generan las sesiones (páginas HTML, artifacts, archivos enviados, diagramas). El HTML se sirve desde un segundo listener del mismo proceso (`127.0.0.1:8771`, `viewer_port`) en **otro origen** (`https://<tu-maquina>.<tu-red>.ts.net:8445`), dentro de un iframe con sandbox. Hay que publicarlo con `tailscale serve` (paso 3 de la sección de Tailscale) y definir `ORQ_VIEWER_ORIGIN` (o `viewer_origin` en `config.toml`). Sin `viewer_origin` la Biblioteca lista los ítems pero no muestra contenido. Nunca `tailscale funnel`.

Las copias locales (`data/biblioteca/`, por contenido, tope 2 GB y 90 días) se desactivan con `biblioteca_copias = false`.

## Tablero en vivo (SSE)

El tablero llega por `/api/events`. Si el navegador acepta gzip, Colmena comprime ese stream (un evento por bloque, sin esperar al siguiente), lo que baja mucho los datos en el celu. Si un proxy o un `tailscale serve` acumula la respuesta y el tablero se queda sin actualizar, se apaga con `sse_gzip = false` en `data/config.toml` (default `true`) y se reinicia el servicio.

## Voz (dictado local)

El botón de micrófono del chat de sesión graba en el navegador y manda el audio al backend, que lo transcribe en la misma máquina con faster-whisper. El texto queda editable y sin enviar. El audio y el texto no salen de la máquina ni se loguean.

```bash
uv run orquestador descargar-modelo   # una sola vez; es la única salida a internet de esta función
```

- Config: `voz_habilitada` (default `true`; en `false` los endpoints dan 404) y `voz_modelo` (default `small`, int8 en CPU). El modelo vive en `data/models/` (0700) y se descarga de memoria tras 10 min sin uso.
- Una transcripción a la vez (si hay otra, responde 409). Límites: 10 MB, 120 s de audio y 90 s de timeout. Formatos: webm, mp4/m4a, ogg, wav (se valida el contenido).
- Atajo en PC: Ctrl+Shift+Espacio empieza y termina; Esc cancela.
- El micrófono requiere HTTPS (`tailscale serve` ya lo es). La app manda `Permissions-Policy: microphone=(self)`; el visor de la Biblioteca sigue con `microphone=()`.
- onnxruntime está fijado a `<1.29`: desde 1.30 incluye telemetría hacia Microsoft que no se puede apagar.

## Terminales


**Cómo funciona.** El tablero lista, debajo de los agentes de cada tab, las terminales que no son de un agente (shells, `npm run dev`, `tail -f`), con el nombre del programa en primer plano (nunca sus argumentos) y si está en el prompt o corriendo. Tocar una abre el visor: salida en vivo con colores, solo lectura. El visor consulta cada 1,5 s solo mientras está abierto y la app visible. La salida se pinta con un parser propio (sin HTML) y nunca se guarda ni se le manda a ningún Claude.

**Cerrar una terminal.** La × de la fila o "Cerrar terminal" en el visor. Si está en el prompt y comparte pestaña, se cierra directo; si está corriendo algo o es la única de su pestaña (se lleva la pestaña), pide confirmar. Nunca cierra sesiones de Claude, el panel de Colmena ni terminales protegidas. Una sesión puede pedirlo con `[colmena-pestana] {"accion":"cerrar","terminal":"<id o nombre>"}` y vos aprobás con Cerrar o No. Endpoint: `POST /api/terminales/cerrar`.

**Escribir está apagado por defecto.** Para prenderlo, en la máquina de Colmena:

```toml
terminales_escritura = true                              # solo `true` sin comillas; cualquier otro valor la deja apagada
terminales_comandos_rapidos = ["git status", "ls -la"]  # opcional, hasta 12
```

y reiniciar (`systemctl --user restart orquestador`). No se puede prender desde la app. Para apagarlo: volver a `false` y reiniciar.

Con la escritura prendida:

1. **Ctrl+C** y **Repetir el último comando**: confirmación en una hoja, sin PIN. Repetir va en dos pasos: sube la línea anterior al prompt y la muestra; solo con "Ejecutar" manda el Enter. Cancelar limpia el prompt.
2. **Escribir un comando**: pide el PIN para abrir una ventana de escritura de 5 minutos como máximo (2 sin usarla), atada a esta sesión y a esta IP; se cierra al salir de la app o con "Cerrar sesiones". Cada comando se confirma viendo el texto exacto, el `cwd` y el programa. Una sola línea, hasta 500 caracteres, sin saltos de línea, tabs ni caracteres invisibles. Solo se escribe si la terminal está en el prompt de una shell (con vim, ssh, python o una contraseña, no).

Nunca se actúa sobre panes de agentes (Claude), sobre los workspaces protegidos ni sobre el pane del propio orquestador. Si la terminal cambió entre que la viste y confirmaste, la acción se rechaza. Cada acción manda un aviso al celu que no se puede apagar y queda en `data/terminales-auditoria.jsonl` (0600, rotación a 1 MB, secretos tapados como `«oculto»` de forma best-effort: no pegues secretos en comandos), visible en "Actividad" dentro del visor. Ningún Claude puede escribir en las terminales por su cuenta: nada llega a ellas sin que lo confirmes vos.

**Ver una terminal desde la notebook** (misma máquina que el guardián, mismo usuario que corre Colmena):

```bash
uv run --project backend orquestador ver              # lista terminales (número, tarjeta, pestaña, tipo, carpeta)
uv run --project backend orquestador ver 2            # engancharse por número
uv run --project backend orquestador ver API          # o por nombre de pestaña / id de sesión
```

Muestra la salida en vivo y reenvía lo que escribas. **Ctrl+]** sale sin matar la terminal. Al entrar avisa `Ctrl+] para salir`. Usa el socket del guardián en `$XDG_RUNTIME_DIR/colmena-guardian/guardian.sock`.

## Reintentos de mensajes

- Un reintento de mensaje a una sesión con el mismo id no se reenvía si el intento anterior pudo haber llegado; se avisa y el siguiente usa otro id.
- "Mejor a tab nuevo / workspace nuevo" de un traspaso se arma en el servidor.

## Ordenar el tablero

Cada tarjeta y cada pestaña tiene una manija (seis puntitos a la izquierda). En la compu aparece al pasar el mouse y se arrastra; en el celu se mantiene apretada un momento (400 ms) y se arrastra; con la manija enfocada, las flechas arriba y abajo también mueven. Las pestañas se mueven solo dentro de su tarjeta y su tab.

- El orden que elegís manda. Una tarjeta o pestaña que necesita que le respondas no se mueve: se queda en su lugar y se resalta.
- Lo nuevo (lo que todavía no ordenaste) aparece arriba, en el orden automático de siempre.
- Se guarda en Colmena (`state.json`, claves `orden_tablero` y `orden_pestanas`), así que se ve igual en todos tus dispositivos y se actualiza solo en los demás.
- "Volver al orden automático", al pie del tablero, borra el orden de tarjetas y de pestañas.

## Retomar sesiones viejas

El botón del reloj, al lado de "Nueva terminal", lista tus sesiones de Claude de los últimos 30 días (hasta 200, la más reciente primero) con un buscador por título, carpeta y última frase. Solo aparecen las de carpetas permitidas y las que no están abiertas en el tablero. Elegís una, le ponés nombre y decidís si va a una tarjeta existente o a una nueva; se abre con `claude --resume` en la carpeta original de la sesión. Cuenta para el mismo tope por hora que "Nueva terminal".

## Contexto de cada sesión

Cada sesión muestra un anillo con el porcentaje de contexto usado, el mismo número que la statusline de la terminal (si hay captura reciente de la statusline se usa esa; si no, el último `usage` del transcript contra la ventana del modelo). El detalle (tokens, ventana, compactaciones) está en el tooltip. En el chat, cada compactación aparece como un separador con el disparador y los tokens antes y después.

## Limpieza de sesiones

El chip "N sesiones quietas" del tablero y el botón "Limpiar sesiones" de la barra (en celu, el menú "Más opciones") abren una hoja que propone tabs o workspaces para cerrar: quietos hace más de 7 días (de 1 a 30 en la hoja; default `limpieza_dias`), tabs sin Claude y sin cambios, o con la rama mergeada (solo con git local, sin fetch). Se elige, se revisa (el servidor valida de nuevo cada fila y desmarca las que cambiaron) y se cierra manteniendo apretado 1 s (Enter sostenido en PC). Cierra de a una sesión, con huella, bloqueos, protegidos e idempotencia. Nunca cierra nada solo. Las filas con proceso corriendo o respuesta sin leer se listan pero no se pueden marcar. Con `?mock=1` hay candidatas de ejemplo.

## Memoria

Índice local de los transcripts de los últimos 30 días, más Engram si está disponible. La búsqueda se hace desde Ajustes > Memoria; los fragmentos se muestran con secretos tapados.

- Índice: SQLite FTS5 en `data/memoria/indice.sqlite` (carpeta 0700, archivos 0600), local y sin LLM, incremental: al arrancar, con cambios del tablero (cada 60 s como mucho). El texto se guarda redactado y los bloques de archivos de entorno se omiten. No se indexan subagentes, sesiones en `/tmp` ni los prefijos de `memoria_excluir`.
- Ajustes > Memoria: estado del índice, si Engram responde, Reindexar (una vez cada 10 min) y Borrar índice.
- Config: `memoria_habilitada` (default `true`), `memoria_excluir` (prefijos de `cwd`), `memoria_retencion_dias` (0 = sigue al transcript), `docker_bin` (vacío = el `docker` del `PATH`).
- Con `?mock=1` en desarrollo, `?mock=1&falla=engram` simula Engram caído.
- Engram se consulta con `docker exec -i <contenedor> engram mcp --tools=mem_search,mem_get_observation,mem_context,mem_timeline`, con lista blanca.

## Historial de avisos

La campana guarda cada aviso que despacha el servidor (sesiones que preguntan, esperan una aprobación o terminan, terminales y pruebas), una entrada por evento aunque no haya dispositivos suscriptos o falle la entrega (queda como no entregado). Se guarda en `data/avisos.json` (0600, fuera de git), con retención de 30 días y 500 entradas. El cuerpo completo solo se registra si algún dispositivo tiene activado el texto en los avisos; si no, queda uno genérico. `GET /api/avisos` pagina de lo nuevo a lo viejo y `POST /api/avisos/leidos` marca hasta un id. El panel se refresca al abrirlo, al volver la app a primer plano y cuando el servidor avisa de uno nuevo; no hay polling. Tocar un aviso lleva a su sesión o su terminal.

## Tareas programadas

Botón del reloj en la barra (o "Tareas programadas" en el menú del celu). Cada tarea es un pedido que corre solo, a una hora, en un repo, con Claude o con Cursor: todos los días, algunos días de la semana o un día por semana.

- Todo viene apagado. El interruptor global se prende con el PIN (apagarlo no lo pide) y cada tarea nace pausada: se reanuda a mano.
- Hay un solo bucle dentro de Colmena que duerme hasta la próxima corrida; no usa cron ni timers del sistema. Corre solo mientras la notebook esté prendida: lo que caiga mientras estuvo apagada o suspendida no se recupera y queda en el historial como "salteada".
- Tope de 2 corridas a la vez, y una tarea no arranca si su corrida anterior sigue abierta. "Correr ahora" no necesita PIN y vale como una corrida más.
- Claude abre una sesión nueva con permisos normales (nunca en modo automático): si algo pide permiso, la sesión espera. Cursor corre con el runner de Cursor y sus propias reglas; si no está disponible, la corrida falla con ese motivo.
- Colmena no programa tareas en su propio repo. Máximo 30 tareas; el historial guarda las últimas 500 corridas.
- Estado en `data/programadas.json` (0600) y `data/programadas-historial.jsonl`, fuera de git.

API (todas dentro de `/api`, con sesión): `GET /programadas`, `GET /programadas/historial`, `POST /programadas`, `PUT|DELETE /programadas/{id}`, `POST /programadas/habilitar` (PIN al prender), `POST /programadas/{id}/pausa` y `POST /programadas/{id}/correr`.

## Compartir Colmena

Para pasarle el proyecto a otra persona sin tu `data/` ni cambios sin commitear:

```bash
uv run orquestador exportar ~/colmena-para-compartir
```

Arma una carpeta nueva con solo lo que está en git (HEAD), le inicializa un repo con un commit genérico y avisa si encuentra en la copia cosas tuyas (nombre, rutas, hosts, mail de git, y los datos del equipo y de la empresa que salen de tu config) para que las revises antes de mandar el zip. No copia `docs/specs`, `docs/plans` ni `docs/research`. Si encuentra algo termina con código distinto de 0; `--permitir-hallazgos` sigue avisando pero sale 0. Podés sumar palabras propias con `[exportar] terminos = ["..."]` en `config.toml`.

## Trabajador Cursor

Una sesión de Claude puede delegar un cambio mecánico (renombres, aplicar un patrón, completar tests ya diseñados) a `cursor-agent`. Regla del kit: `kit/reglas/colmena/trabajador-cursor.md`.

**Cómo se pide.** La sesión hace `echo '[colmena-pestana] {"accion":"cursor","carpeta":"…","nombre":"…","pedido":"…"}'` (`modelo` opcional). Te llega una tarjeta "Trabajador Cursor" con la carpeta, el pedido y los botones **Lanzar** y **No**; vence en 10 minutos. No se puede pedir en el repo de Colmena.

**Qué hace al lanzarlo.** Crea una copia (worktree) aparte en la rama `cursor/<nombre>-<4 hex>` desde el último commit de la carpeta y corre `cursor-agent -p --output-format stream-json --trust --sandbox enabled --workspace <copia>` con el pedido por stdin. Nunca usa `--force`, `--yolo` ni aprobaciones automáticas: Cursor edita archivos y solo corre los comandos que tu configuración de Cursor permite; el prompt le pide no correr comandos ni commitear, pero Colmena no lo puede impedir, así que conviene revisar `git log` y `git diff` de la copia. Al terminar, la sesión que lo pidió recibe "Colmena: terminó el trabajador Cursor…" con la rama y los archivos tocados (el resumen de Cursor va marcado como dato) y la revisa ella.

**Topes.** 2 a la vez, 6 por hora, 45 minutos cada uno (después se corta), log de hasta 5 MB. Si el guardián se reinicia, los que estaban corriendo quedan como "Interrumpido". Registro en `data/cursor/trabajadores.json`, logs en `data/cursor/<id>/`.

**Rutas.** `GET /api/cursor/estado`, `GET /api/cursor/trabajadores`, `GET /api/cursor/trabajadores/{id}/log` y `POST /api/cursor/trabajadores/{id}/cancelar`. No hay ruta para lanzar: solo se lanza aprobando un pedido.

## Nueva tarea y tickets

Desde la nueva tarea (`POST /api/terminales/nueva-tarea`) elegís un repo y escribís el pedido. Colmena crea una copia del repo (git worktree) con su propia rama y abre ahí una sesión de Claude. La rama sale del pedido: `feature/<ticket>` si trae una clave de Jira, `feature/<slug>` si no (en el repo de Colmena, `feature/kit-<slug>`). Podés fijar la rama a mano. Al borrar la tarea, la copia solo se borra si no pierde trabajo (sin cambios sin guardar y rama integrada en la base).

Con un ticket (por ejemplo `ABC-123`, validado como clave de Jira) la sesión recibe un mensaje que le pide leer el ticket con un agente de tickets y seguir un flujo de trabajo (por defecto `/flujo-tickets`); ese agente y ese flujo vienen de tu kit de trabajo, así que el mensaje solo sirve si lo tenés instalado. Sus nombres se configuran en `[kit_trabajo]` (`agente_tickets`, `comando_flujo`). Colmena no habla con Jira: solo pasa la clave. La nota que sumes se agrega al mensaje y tiene un tope de largo.

## Comentarios del diff

En los cambios de una sesión podés marcar un rango de líneas (nuevas o borradas) y escribir un comentario. Hasta 10 comentarios por vez se mandan a esa sesión en un solo mensaje (`POST /api/sesiones/{sid}/cambios/comentarios`) que le pide aplicarlos en su rama y preguntar si alguno no cierra. Antes de mandar, el backend revisa que la carpeta de la sesión sea una permitida, que el archivo siga entre los cambios y que el fragmento siga en el diff; si cambió, pide actualizar. Los fragmentos viajan marcados como datos, no como instrucciones.

## MRs a la sesión

Con los MRs de GitLab configurados, desde un MR podés mandar a una sesión abierta de Claude:

- la cola del log de un job fallido o cancelado del último pipeline (`POST /api/mrs/{pid}/{iid}/jobs/{job_id}/a-sesion`);
- los últimos comentarios de un hilo del MR (`POST /api/mrs/{pid}/{iid}/hilos/{hilo_id}/a-sesion`).

`GET /api/mrs/{pid}/{iid}/destinos` lista las sesiones posibles y sugiere la asociada a la rama del MR. Solo recibe ids: el contenido lo lee el backend de GitLab y lo manda marcado como datos, con el texto de los comentarios pasado por un filtro de secretos. La sesión tiene que estar esperando (si trabaja o espera una aprobación, responde 409) y un mismo envío repetido enseguida se rechaza.

## Uso del plan de Claude

La barra muestra el porcentaje usado de los límites de 5 horas y de 7 días del plan, con la hora en que se reinician. Los datos salen de lo que la statusline de Claude Code guarda en el disco: Colmena no llama a ninguna API. `GET /api/uso/limites` devuelve esos datos (o `sin_datos` si todavía no hay ninguno, y marca como vencido un límite que ya se reinició). `GET /api/uso/claude` suma los tokens de tus sesiones por día y modelo, leídos de los transcripts locales.

## Desarrollo

```bash
uv run pytest                                   # backend
cd frontend && npx vitest run                   # frontend
cd frontend && npm run dev                      # http://127.0.0.1:5173 (proxy /api a :8770)
# http://127.0.0.1:5173/?mock=1 -> datos falsos, sin backend
```

Con `tailscale_user` configurado, el listener Tailscale exige `Tailscale-User-Login`: el proxy de Vite y cualquier cliente directo al puerto 8770 reciben 403. Para desarrollar, usá el modo `solo-local` (puerto 8774) o dejá `tailscale_user` vacío en la config de desarrollo.

## Archivos huérfanos en `data/`

Centinela se quitó el 2026-11-15. Si existen en `data/`, estos archivos ya no los usa nadie y se pueden borrar a mano: `centinela*`, `centinela-aprueba.json`, `novedades.json`, `planes.json`, `encargos.json`, `bandeja.json`, `frentes.json`, `memoria-mcp.json` y `memoria-auditoria.jsonl`.

- `dios-ajustes.json` se sigue leyendo: es la herencia de la config de MRs (`mrs_*` → `data/dios-ajustes.json` → `dios_*`).
- `uso.json` puede tener entradas viejas con fuente `dios`; son inofensivas.

## Antes de publicar una copia

Antes de armar el ZIP con `git archive`, corré `scripts/revisar-publicable.sh`: extrae `HEAD` a un directorio temporal y busca, sin distinguir mayúsculas, las palabras de una lista propia que no se versiona (`~/.config/colmena/palabras-prohibidas.txt`, una por línea; las excepciones por falsos positivos van en `~/.config/colmena/palabras-excepciones.txt`, opcional). Sale con código distinto de 0 y lista `archivo:línea` si encuentra algo. Revisa lo commiteado, no el árbol de trabajo.

## Licencia

[MIT](LICENSE) © 2026 Andoni Gallego
