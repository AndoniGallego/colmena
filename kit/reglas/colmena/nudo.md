# El nudo: señalar controles en la PC de Ando

> Esta regla rige cuando la sesión corre en una terminal de Colmena (COLMENA_TERMINAL=1). Si no sabés, aplicala.

<!-- propósito: La sesión puede marcarle a Ando, en la pantalla de su PC, qué control tocar; solo cuando ayuda y limpiando al terminar. -->

El nudo dibuja un globo o una marca sobre un control de la app que Ando tiene al frente en la PC Windows. Usalo solo si le sirve: mostrarle algo en pantalla, guiarlo en una prueba o en una demo. No lo uses si Ando está en el celu o fuera de la PC, ni para algo que se explica en una línea de texto.

- `orquestador nudo controles`: lista los controles de la ventana al frente. Siempre antes de señalar, y de nuevo ante `foto vieja` (la ventana cambió).
- `orquestador nudo senalar <n> "<texto>"`: globo sobre el control `n` de la última lista. Texto corto, en una línea, hasta 120 caracteres.
- `--esperar` (en `senalar`): se queda esperando que Ando toque el control o apriete Listo. Solo si tu paso siguiente depende de que lo haga. El aviso `usado` puede no llegar: Listo es el camino seguro.
- `orquestador nudo marcar 12:Guardar 14:Cancelar`: marcas con etiqueta (hasta 8 por vez).
- `orquestador nudo limpiar`: saca tu dibujo. Hacelo siempre al terminar.
- `orquestador nudo estado`: cómo está el nudo.

Si algo falla:

- `apagado`: decile a Ando que está apagado y seguí con texto. Nunca le pidas que lo prenda para la sesión ni cambies su visibilidad.
- `ocupado` (lo usa otra sesión) o `en_curso`: no reintentes en bucle; seguí con texto.
- `sin controles accesibles`: esa app no informa sus controles; explicalo con texto.
- Sin PC conectada, Colmena caída, `sin ventana`, `vencido` o `fallo_pc`: seguí con texto, sin insistir.
