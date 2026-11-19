# Informe de pruebas

> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.

<!-- propósito: Al terminar una ronda de pruebas, la sesión la resume en una tarjeta con ✓, ✗ y capturas. -->

Ando sigue las sesiones desde la app Orquestador (Colmena), muchas veces desde el celu. Cuando una sesión prueba algo (una página en el navegador, un endpoint, un flujo en una tienda, tests a mano), Ando quiere ver de un vistazo qué se probó y qué dio, sin leer toda la conversación. La app dibuja un bloque `pruebas` como una tarjeta con un ✓, ✗ o – por caso y lo guarda en la Biblioteca para encontrarlo después.

Cuando terminás una ronda de pruebas, poné un bloque `pruebas` en el mensaje donde contás el resultado:

```pruebas
{"titulo": "Home de categorías en el celu", "resumen": "Probé la home nueva en la tienda local, a 390px y en escritorio",
 "casos": [
  {"nombre": "Carga la pestaña Novedades", "resultado": "ok", "evidencia": "ss_1617g80dx"},
  {"nombre": "Carrusel a 390px de ancho", "resultado": "ok", "evidencia": "/tmp/claude-1000/ejemplo/scratchpad/carrusel-390.png"},
  {"nombre": "Ajax con categoría inválida", "resultado": "falla", "detalle": "Devolvió 500; esperaba 404 o una lista vacía"},
  {"nombre": "Pago", "resultado": "omitida", "detalle": "Este cambio no toca el checkout"}]}
```

Uno chico:

```pruebas
{"titulo": "Login con el usuario de prueba", "casos": [
  {"nombre": "Entra con el DNI de prueba", "resultado": "ok"},
  {"nombre": "Muestra el nombre en el encabezado", "resultado": "ok"}]}
```

## Qué poner

- Un caso por cosa que verificaste, con un `nombre` que diga qué se probó en lenguaje de usuario ("Carrusel a 390px", no "test_carousel_resize").
- `resultado`: `ok`, `falla` u `omitida` (no se probó, y en `detalle` por qué).
- `detalle`: qué pasó cuando no es obvio. En una falla, lo que viste y lo que esperabas.
- `evidencia`: una captura que respalde el caso. Si la sacaste con el Chrome (claude-in-chrome), poné el ID que te devolvió la captura (`ss_…`, aparece en su resultado como `ID: ss_…`); Colmena la busca en la sesión y la muestra en el caso. Si es un archivo de imagen, su ruta absoluta (png, jpg, webp o gif); Colmena la copia a la Biblioteca, así que no se pierde aunque se borre el scratchpad. Si un caso tuvo captura, ponela siempre. Si la evidencia no es una imagen (una respuesta JSON, un log), resumila en `detalle`.
- Solo lo que realmente probaste y viste. Si no llegaste a verificar algo, va como `omitida`, nunca como `ok`.

## Formato

- `titulo` (hasta 100 caracteres) y `casos` (de 1 a 60) son obligatorios; `resumen` (hasta 300) es opcional.
- Cada caso: `nombre` (hasta 120) y `resultado` obligatorios; `detalle` (hasta 400) y `evidencia` (ruta absoluta, hasta 500, o ID `ss_…`) opcionales.
- Un bloque por ronda de pruebas. Si hay varias rondas en el mismo mensaje, un bloque por cada una.
- El JSON tiene que ser válido; si no, la app lo muestra como código.
- Va antes del bloque `estado`, que sigue cerrando el mensaje. En el `hizo` del estado conviene el resumen corto ("Probé la home: 3 ok, 1 falla").
