# Compilar Colmena en Windows

Guía para armar el instalador de la app de Windows de Colmena (notch y ventana Entornos) en una PC con Windows (PowerShell). Es opcional: Colmena funciona sin esta app.

## 1. Build Tools de Visual Studio 2022

Instalá las herramientas de compilación con la carga de trabajo de escritorio en C++ (trae MSVC y el SDK de Windows):

```powershell
winget install Microsoft.VisualStudio.2022.BuildTools
```

En el instalador, tildá **Desarrollo para el escritorio con C++**.

## 2. Rust y Node

```powershell
winget install Rustlang.Rustup
winget install OpenJS.NodeJS.LTS
```

Cerrá y volvé a abrir PowerShell, después:

```powershell
rustup default stable-msvc
cargo --version
node --version
```

En Windows 11, WebView2 ya viene instalado.

## 3. Traer el código

Te pasan el proyecto en un **ZIP** (sin carpeta `.git`).

1. Descomprimí el ZIP en una ruta **sin espacios**, por ejemplo `C:\dev\colmena`.
2. Abrí PowerShell en esa carpeta (`cd C:\dev\colmena`).

Para **actualizar** más adelante: borrá la carpeta vieja (o descomprimí el ZIP nuevo encima, reemplazando archivos) y repetí desde el paso 4.

## 4. Tests del núcleo

```powershell
cargo test --manifest-path windows\colmena-app\nucleo\Cargo.toml
```

Tiene que terminar con todos los tests en verde (`test result: ok`, sin `FAILED`).

## 5. Build del instalador

```powershell
cd windows\colmena-app
npm install
npm run tauri icon ..\..\frontend\public\icons\icon-512.png
npm run build
```

El instalador queda en:

`src-tauri\target\release\bundle\nsis\Colmena_*_x64-setup.exe`

## 6. Primera ejecución

Instalá y abrí Colmena. La primera vez pide la dirección del servidor, por ejemplo:

`https://<tu-maquina>.<tu-red>.ts.net:8444` (la de `ORQ_APP_ORIGIN`, ver el README)

## 7. Avisos en Chrome (una sola vez)

En la app de Chrome de la PC: **Ajustes → Avisos → Desactivar**. Después podés desinstalar la app de Chrome si querés.

## 8. Si algo falla

Anotá qué paso falló, el mensaje de error y una captura, y pasáselo a quien te mandó el ZIP. Con el ZIP corregido, repetí desde el **paso 3**.

---

## Verificación manual

Marcá cuando pruebes cada ítem. Aviso: la app ya no trae una notebook por defecto; si esta PC no la tenía guardada en `config.json`, hay que cargarla una vez (bandeja → "Dirección de la notebook…") antes de las pruebas 14 a 21.

- [ ] **1.** Primer arranque: pide la dirección; rechaza `http://…` y una URL con ruta; acepta la dirección HTTPS completa de Colmena (`https://<tu-maquina>.<tu-red>.ts.net:8444`).
- [ ] **2.** Notch arriba al centro del monitor principal, sin bordes, fondo transparente, siempre arriba y sin ícono en la barra de tareas. Arrastrar la pastilla la mueve (también a otro monitor) y queda ahí al reiniciar; un clic sin mover abre el panel; cerca de un borde el panel se corre para entrar; Monitor del notch la devuelve centrada arriba.
- [ ] **3.** Escribiendo en el Bloc de notas, llega un aviso de pregunta: suena una vez y el texto sigue entrando en el Bloc (el notch no robó el foco).
- [ ] **4.** Clic en el notch: se despliega; "Otra cosa…" recibe el teclado; Esc lo cierra.
- [ ] **5.** Un clic a más de 2 cm de la pastilla llega a la ventana de abajo.
- [ ] **6.** El PIN se pone una vez; "Abrir Colmena" abre la ventana grande sin pedirlo de nuevo; tocar un renglón abre esa sesión.
- [ ] **7.** En la ventana grande, Ajustes → Avisos dice "En el programa de Windows los avisos salen del notch.".
- [ ] **8.** Con la ventana grande cerrada y el notch a la vista, un aviso igual llega al celu (el notch no reporta presencia).
- [ ] **9.** Bandeja: mostrar u ocultar, abrir, "Arrancar con Windows" (cerrar sesión de Windows y volver a entrar) y salir. Desde la bandeja, **Monitor del notch**: el notch se muda al monitor elegido y queda ahí al reiniciar.
- [ ] **10.** Abrir el programa por segunda vez trae al frente lo que ya estaba, sin otra instancia.
- [ ] **11.** Cortar el wifi: el logo se apaga; al volver, reconecta solo.
- [ ] **12.** Con build de depuración (`npm run tauri build -- --debug`), en DevTools del notch: `__TAURI__.core.invoke('guardar_origen', { origen: 'https://x' })` falla. En la ventana grande, `__TAURI__.core.invoke('notch_tamano', { ancho: 300, alto: 60, foco: false })` y `__TAURI__.core.invoke('notch_arrastrar')` también fallan.
- [ ] **13.** Consola del notch: si aparece un error de CSP por `ipc.localhost` pero los comandos igual funcionan, anotarlo; si no funcionan, es disparador del plan B.
- [ ] **14.** Bandeja → "Entornos": la ventana grande abre en Entornos; arriba "Notebook: `<usuario>@<dirección>`" si ya la configuraste, o "Configurá la notebook" si no (la app no trae ninguna por defecto: sin notebook guardada no intenta conectarse a nada); aparecen los entornos Docker que corren (por ejemplo `ps9`) con carpeta y puertos.
- [ ] **15.** "Abrir" en `ps9`: el navegador por defecto abre `http://localhost:<puerto>/` (por ejemplo 8080); la tienda carga con estilos, el admin entra sin redirigir y el login de prueba (8092) anda. La tarjeta dice "Túnel abierto" y cada `localhost:<puerto>` abre su puerto. Un doble clic rápido en "Abrir" no abre dos túneles.
- [ ] **16.** `netstat -ano | findstr :8080` con el túnel abierto: solo `127.0.0.1:8080`, nunca `0.0.0.0:8080`.
- [ ] **17.** Puerto ocupado: con `python -m http.server 8080 --bind 127.0.0.1` corriendo, "Abrir" en `ps9` dice "el puerto 8080 ya está en uso en esta PC". Repetir con `python -m http.server 8080` (sin `--bind`): la tarjeta queda en error (de la prueba o de `ssh`), nunca en "Túnel abierto".
- [ ] **18.** "Cerrar túnel": la tarjeta vuelve a "Túnel cerrado" y `http://localhost:8080` deja de cargar.
- [ ] **19.** Bandeja → "Dirección de la notebook…": rechaza `-oProxyCommand=calc` y el usuario `Cc`; con una dirección inexistente de tu red, "Abrir" muestra "No llego a la notebook. ¿Estás en la red de casa y la dirección es la correcta?" y el error original. Volver a la dirección correcta. El enlace "cambiar" de la vista abre la misma ventana.
- [ ] **20.** Con dos túneles abiertos, "Salir" desde la bandeja; después `Get-Process ssh -ErrorAction SilentlyContinue` no muestra nada.
- [ ] **21.** Build de depuración, DevTools del notch: `__TAURI__.core.invoke('entornos_estado')` falla. En la ventana grande: `invoke('entorno_abrir', { nombre: 'x', puertos: [8770], principal: 8770 })` da "el puerto 8770 está bloqueado por seguridad"; `invoke('guardar_notebook', { host: '1.2.3.4', usuario: 'cc' })` y `invoke('plugin:opener|open_url', { url: 'https://example.com' })` fallan. Lo mismo con los comandos de la ventana Atajos, desde el notch y desde la ventana grande: `invoke('leer_atajos')`, `invoke('pausar_atajos')`, `invoke('reanudar_atajos')`, `invoke('probar_atajo', { accion: 'notas', ctrl: true, alt: true, shift: false, code: 'KeyN' })` e `invoke('guardar_atajo', { accion: 'notas', atajo: 'Ctrl+Alt+N' })` fallan con "no permitido".
- [ ] **22.** En Chrome, fuera de la app, la dirección de Colmena seguida de `/entornos`: lista sin botones y con "Para abrir entornos usá la app de Windows". Con Entornos abierto, cerrar sesión (PIN) y volver a entrar: Entornos no reaparece solo.
- [ ] **23.** Pedido de pestaña en el notch: cuando una sesión pide abrir otra pestaña, el notch muestra el pedido con **Abrir** y **No**. "Abrir" abre la pestaña y el pedido desaparece; "No" lo descarta. Un pedido sin decidir vence a los 10 minutos.
- [ ] **24.** Atajo de notas: **Ctrl+Alt+N** muestra el notch y abre el modo notas (el cuadro para escribir). Probalo también recién arrancada la app, apretando el atajo enseguida, antes de que el notch termine de cargar: el modo notas tiene que abrirse igual apenas cargue.
- [ ] **25.** Desde el notch, guardar un apunte y un recordatorio: los dos quedan guardados y aparecen en el panal de notas de la ventana grande.
- [ ] **26.** En el panal, marcar una nota como hecha y apretar **Deshacer**: la nota vuelve a pendiente y el contador del notch acompaña.
- [ ] **27.** Bandeja → **Atajos**: tres renglones grises ("Notas: Ctrl+Alt+N", "Notch: Ctrl+Alt+M", "Colmena: Ctrl+Alt+C") y **Cambiar atajos…**, que abre la ventana Atajos (no se puede agrandar). Con la ventana abierta, los tres atajos siguen andando.
- [ ] **28.** Grabar y guardar: en la ventana, **Cambiar** en Notas: la fila dice "Apretá la combinación…" y los tres atajos globales dejan de andar mientras graba. Apretá `Ctrl+Shift+Space`: muestra la combinación con **Guardar** y **Cancelar**. Guardar: la fila queda con el atajo nuevo, ese abre las notas, el anterior ya no, y los atajos globales vuelven. El renglón de la bandeja se actualiza. Reiniciá la app: sigue el nuevo.
- [ ] **29.** Cancelar: **Cambiar** y después **Cancelar** (o Esc, o cerrar la ventana a mitad de la grabación): el atajo queda como estaba y los tres atajos globales vuelven a andar.
- [ ] **30.** Inválido: grabando, probá `Ctrl+K` (un solo modificador), `Ctrl+Alt+Q` y `Ctrl+Alt+2` (AltGr) y `Ctrl+Shift+Enter` (tecla no permitida). Cada uno muestra en la misma fila un error en castellano claro y deja seguir grabando. `Alt+F4`, `Ctrl+Esc` y la tecla Windows no sirven para esta prueba: Windows las atrapa antes (cierra la ventana o abre Inicio). Alcanza con que no se guarde nada y los atajos sigan andando al volver.
- [ ] **31.** Duplicado: poné en Notch el atajo que tiene Notas. Error "Ya lo usa Notas" en la fila, sin guardar.
- [ ] **32.** Ocupado: con otro programa usando `Ctrl+Shift+Space`, grabalo y guardalo. Error "Lo usa otro programa: queda …" en la fila, y el atajo anterior sigue andando (también tras reiniciar la app). Arrancá la app con un atajo guardado que otro programa ya usa: en Atajos de la bandeja aparece la línea gris "El atajo de X lo usa otro programa" y la ventana lo avisa en la fila.
- [ ] **33.** **Volver al de fábrica** (aparece solo en la fila que cambió): vuelve a `Ctrl+Alt+N`, `Ctrl+Alt+M` o `Ctrl+Alt+C` y desaparece el enlace.
- [ ] **34.** Los atajos nuevos: **Ctrl+Alt+M** oculta el notch si está visible y lo muestra si estaba oculto. **Ctrl+Alt+C** trae la ventana grande de Colmena al frente (también si está minimizada o escondida) sin recargarla, y si no estaba abierta, la abre.
- [ ] **35.** Migración: con un `config.json` de una versión anterior que tenga `"atajo_notas": "Ctrl+Shift+Space"`, al arrancar Notas usa ese atajo y Notch y Colmena usan los de fábrica.
- [ ] **36.** Pedidos en el notch: desde una sesión de Claude, pedí abrir una pestaña (`[colmena-pestana]`). La sesión aparece en **Te toca** del notch con **Abrir** y **No**; Abrir la abre y el pedido desaparece también del chat y de la campana. Repetí pidiendo cerrar una sesión de prueba (`{"accion":"cerrar","sesion":"…"}`): el renglón muestra el id y el espacio de lo que se va a cerrar, y si esa sesión está trabajando el botón dice **Cerrar igual**. **No** lo descarta sin cerrar nada.
- [ ] **37.** Sin notebook guardada: con un `config.json` sin la clave `notebook`, Entornos muestra "Configurá la notebook" arriba y, al apretar Abrir en un entorno, dice "Configurá la notebook primero…" sin lanzar ningún `ssh` (`Get-Process ssh` no muestra nada). "cambiar" abre la ventana Notebook con los campos vacíos; tras guardar la dirección y el usuario, Entornos los muestra y Abrir anda.
