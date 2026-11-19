# Comandos que pide la sesión: un bloque `comando`

> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.

<!-- propósito: Cuando la sesión necesita que corras un comando, lo pide en una tarjeta con Correr y No. -->

Ando sigue las sesiones desde Colmena (PC y celu). Si le pedís "corré esto en una terminal", tiene que abrir una terminal, poner el PIN y tipearlo: es lo más tedioso de su día. En cambio, un bloque `comando` en tu mensaje aparece como una tarjeta con el comando y dos botones, **Correr** y **No**. Al tocar Correr, Colmena lo escribe en tu propia sesión en modo bash de Claude Code (`!comando`): corre en tu terminal y la salida te queda en la conversación.

## Cuándo usarlo

Solo cuando no lo podés correr vos:

- El sandbox o los permisos te lo frenan y el comando es necesario.
- Pide algo interactivo o una credencial que solo tiene Ando (un login: `glab auth login`, `gcloud auth login`, `npm login`).
- Necesita que Ando lo decida (borrar algo, reiniciar un servicio suyo).

Lo que podés hacer con tus herramientas lo hacés vos, sin pedírselo: actualizar un MR (descripción, labels, reviewer), comentar, correr tests, consultar el estado de un pipeline. No conviertas tu trabajo en un pedido a Ando.

## Formato

Un comando por bloque. Si necesitás dos, dos bloques, en el orden en que se corren.

```comando
{"comando": "glab auth login --hostname gitlab.com", "motivo": "Tu sesión de GitLab venció y sin eso no puedo leer el MR"}
```

```comando
{"comando": "docker compose restart php", "motivo": "El contenedor quedó con la configuración vieja; reiniciarlo la carga", "carpeta": "/home/usuario/development/ps9"}
```

- `comando` (obligatorio): una sola línea, hasta 500 caracteres, sin caracteres invisibles ni de control, sin espacios al principio o al final, y que no empiece con `-`. Colmena muestra exactamente este texto y corre exactamente este texto; si no cumple, la tarjeta sale sin el botón Correr.
- `motivo` (obligatorio): para qué sirve, en lenguaje simple y una frase (hasta 200 caracteres). Ando decide con esto, muchas veces desde el celu.
- `carpeta` (opcional): tiene que ser la carpeta actual de tu sesión, que es donde corre el comando; Colmena muestra la carpeta real y, si la que ponés no coincide, la tarjeta queda inválida. Si hace falta correrlo en otra carpeta, ponelo en el comando (`cd /ruta && ...`) y omití `carpeta`.
- El JSON tiene que ser válido.

## Reglas

- Nunca pongas un secreto en el comando (tokens, contraseñas, claves): queda en la conversación y en la auditoría. Si hace falta uno, que el comando lo pida de forma interactiva o lo lea de donde ya está.
- Solo se puede correr cuando terminaste el turno (la sesión esperando). Por eso el bloque va en tu mensaje final, y después no sigas trabajando: esperá.
- Cada bloque se corre una sola vez, y solo los del último mensaje: si la conversación siguió, pedilo de nuevo.
- La salida te llega como resultado del comando `!`, pero Claude Code no te despierta solo: la vas a ver cuando Ando te escriba. Si necesitás seguir apenas termine, decíselo en el motivo o en el texto ("cuando termine, escribime *listo*").
- Nada de cadenas largas con `;` para meter varios pasos en un comando: uno por bloque, así Ando ve qué aprueba.
