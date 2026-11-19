# Preguntas con opciones

> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.

<!-- propósito: Las preguntas con opciones llegan como botones, no como diálogos de la terminal. -->

Ando maneja las sesiones desde la app Orquestador (celular y PC), que no puede contestar los diálogos de la terminal. Por eso:

- No usar AskUserQuestion. Las preguntas van en el texto de la respuesta.
- Cuando la pregunta es elegir entre opciones, escribirla como un bloque `opciones`. La app lo muestra como una tarjeta con un botón por opción, y al tocar uno llega como mensaje `<n>. <label>`.

```opciones
{"pregunta": "¿Qué hacemos con X?", "opciones": [
  {"label": "Recortarlo", "detalle": "Qué implica, en una línea", "recomendada": true},
  {"label": "Sacarlo", "detalle": "Qué implica, en una línea"}
]}
```

- Entre 2 y 6 opciones; `label` corto (hasta 80 caracteres), `detalle` hasta 200, `pregunta` hasta 300. La recomendada va primera y con `"recomendada": true`.
- El JSON tiene que ser válido; si no, la app lo muestra como código.
- Antes del bloque, el contexto que haga falta para decidir. Una sola pregunta por bloque; si hay varias, un bloque por cada una.
- Las preguntas abiertas (sin opciones cerradas) van como texto normal.
