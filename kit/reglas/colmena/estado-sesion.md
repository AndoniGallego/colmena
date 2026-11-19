# Estado de la sesión al cerrar

> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.

<!-- propósito: Al terminar o preguntar, la sesión cierra con tres líneas (qué hizo, qué falta, qué pide) para la tarjeta. -->

Ando sigue las sesiones desde la app Orquestador (Colmena), muchas veces desde el celu y sin abrir el chat. La tarjeta de cada sesión muestra en tres líneas en qué quedó, y las lee de un bloque `estado` al final de tu mensaje.

Cuando terminás un trabajo, quedás esperando al usuario o le hacés una pregunta, cerrá el mensaje con un bloque `estado`:

```estado
{"hizo": "Saqué el mapa y reinicié Colmena", "falta": "Elegir el diseño de las tarjetas", "pide": "¿Cuál de las tres opciones preferís?"}
```

- `hizo`: lo que quedó hecho en este tramo, en una frase.
- `falta`: lo que queda pendiente, si hay algo.
- `pide`: lo que necesitás del usuario (una decisión, un OK, un dato), si hay algo. Si no le pedís nada, no lo pongas.
- Los tres campos son opcionales, pero al menos uno tiene que tener texto; poné solo los que tengan algo que decir. Hasta 120 caracteres cada uno.
- Lenguaje simple, sin jerga ni nombres de archivos: tiene que entenderse de un vistazo en el celu.
- Un solo bloque, al final del mensaje (después de un bloque `opciones` si lo hay). El JSON tiene que ser válido.
- Si en el turno usaste herramientas (leer, buscar, correr algo), el bloque va siempre: en las terminales de Colmena un control frena el cierre si falta.
- No lo pongas en mensajes intermedios mientras seguís trabajando. Las respuestas rápidas que no usaron herramientas no lo necesitan.
