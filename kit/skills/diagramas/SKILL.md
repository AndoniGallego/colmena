---
name: diagramas
description: Formato del bloque ```diagrama que la app Colmena dibuja (estructura, secuencia, proceso). Usar cuando Ando pide explicar una arquitectura, cómo se comunican las cosas, un proceso o un plan.
---

Ando maneja las sesiones desde la app Orquestador (celular y PC). Cuando pide que le expliques algo (una arquitectura, cómo se comunican las cosas, un proceso, un plan), respondé con un texto breve y un bloque `diagrama`: la app lo dibuja entero, al tocar un nodo muestra su detalle y se puede ampliar a pantalla completa con zoom.

Hay tres tipos de diagrama, que se eligen con `"tipo"`:

- `estructura` (el default si no ponés tipo): estructura y relaciones, quién habla con quién, dónde vive cada cosa, de qué partes está hecho algo.
- `secuencia`: actores que se mandan mensajes en el tiempo, con pasos numerados.
- `proceso`: pasos con decisiones de sí/no.

Las secuencias y los procesos tienen un botón "Recorrer" para verlos paso a paso.

Estructura con grupos:

```diagrama
{"tipo": "estructura", "titulo": "Cómo te llegan los avisos", "resumen": "Quién habla con quién desde que Claude termina hasta que suena tu celu",
 "grupos": [{"id": "compu", "nombre": "Tu compu", "color": "azul"}, {"id": "afuera", "nombre": "Afuera", "color": "violeta"}],
 "nodos": [
  {"id": "claude", "nombre": "Claude", "icono": "🤖", "tipo": "app", "grupo": "compu", "detalle": "Trabaja en tus proyectos y avisa cuando termina"},
  {"id": "orq", "nombre": "Orquestador", "icono": "🧭", "tipo": "servicio", "grupo": "compu", "detalle": "Decide cuándo vale la pena avisarte, así no te llenás de ruido"},
  {"id": "bib", "nombre": "Biblioteca", "icono": "📚", "tipo": "datos", "grupo": "compu", "detalle": "Guarda lo que van armando las sesiones para que lo encuentres después"},
  {"id": "celu", "nombre": "Tu celu", "icono": "📱", "tipo": "app", "grupo": "afuera", "detalle": "Te muestra el aviso aunque tengas la app cerrada"},
  {"id": "vos", "nombre": "Vos", "icono": "🙂", "tipo": "persona"}],
 "conexiones": [
  {"de": "claude", "a": "orq", "texto": "cuenta que terminó"},
  {"de": "claude", "a": "bib", "texto": "guarda lo que armó", "tipo": "datos"},
  {"de": "orq", "a": "celu", "texto": "manda el aviso"},
  {"de": "celu", "a": "vos", "texto": "te lo muestra"},
  {"de": "vos", "a": "orq", "texto": "respondés", "tipo": "respuesta"}],
 "notas": ["Los avisos se apagan desde Ajustes"]}
```

Uno chico, sin grupos:

```diagrama
{"titulo": "Dónde vive cada cosa",
 "nodos": [
  {"id": "app", "nombre": "La app", "icono": "📱", "tipo": "app", "detalle": "Lo que ves en el celu y en la compu"},
  {"id": "srv", "nombre": "El servidor", "icono": "⚙️", "tipo": "servicio", "detalle": "Corre en tu compu y arma todo lo que la app muestra"},
  {"id": "db", "nombre": "Tus datos", "icono": "🗄️", "tipo": "datos", "detalle": "Lo que se guarda para que no se pierda al reiniciar"}],
 "conexiones": [
  {"de": "app", "a": "srv", "texto": "pide"},
  {"de": "srv", "a": "db", "texto": "guarda y lee", "tipo": "datos"},
  {"de": "srv", "a": "app", "texto": "responde", "tipo": "respuesta"}]}
```

Secuencia (actores que se mandan mensajes):

```diagrama
{"tipo": "secuencia", "titulo": "Cómo te llega un aviso", "resumen": "De que Claude termina a que suena tu celu",
 "actores": [{"id": "claude", "nombre": "Claude", "icono": "🤖"}, {"id": "orq", "nombre": "Orquestador", "icono": "🧭"}, {"id": "celu", "nombre": "Tu celu", "icono": "📱"}],
 "pasos": [
  {"de": "claude", "texto": "Claude termina de trabajar en la compu", "detalle": "Queda esperando tu próxima indicación", "tipo": "evento"},
  {"de": "claude", "a": "orq", "texto": "Claude le avisa al Orquestador que terminó", "detalle": "Así el Orquestador sabe que te toca a vos", "tipo": "llamada"},
  {"de": "orq", "a": "celu", "texto": "El Orquestador le manda un aviso a tu celu", "detalle": "Te llega aunque tengas la app cerrada", "tipo": "llamada"},
  {"de": "celu", "texto": "Tu celu suena y te muestra el aviso", "tipo": "evento"}],
 "notas": ["Si no querés avisos, se apagan desde Ajustes"]}
```

Proceso (pasos con decisiones):

```diagrama
{"tipo": "proceso", "titulo": "Cocinar un bife",
 "pasos": [
  {"id": "p1", "texto": "Sellar la carne", "duracion": "3 min", "icono": "🔥"},
  {"id": "p2", "texto": "Revisar el punto", "decision": {"pregunta": "¿Está dorada?", "si": "p3", "no": "p1"}},
  {"id": "p3", "texto": "Dejar descansar", "duracion": "5 min", "icono": "😌"}]}
```

## Cómo escribirlo para que lo entienda cualquiera

El diagrama tiene que entenderlo alguien que no sabe nada técnico.

- Pocos nodos, idealmente 8 o menos (5 o menos actores en una secuencia), con nombres que se entiendan ("la compu", "tu celu", "el Orquestador"), no nombres de procesos o archivos.
- `texto` de una conexión: un verbo corto que diga qué pasa ("manda el aviso", "guarda lo que armó"). En una secuencia o un proceso, cada paso es una frase completa con sujeto y verbo.
- Nada de jerga (transcript, jsonl, socket, VAPID, endpoint, cookie, payload...) salvo que el usuario la pida. Si hace falta un término, se explica en `detalle`.
- `detalle` dice el para qué ("así te enteras sin mirar la pantalla"), no el cómo técnico.
- Grupos solo si ayudan a ver dónde vive cada cosa (por ejemplo "Tu compu" y "Afuera").

## Formato

- `estructura`: `nodos` (hasta 40) con `id` corto y `nombre` (hasta 60 caracteres); opcionales `icono` (un emoji), `detalle` (hasta 400), `grupo` (id de un grupo) y `tipo`: `persona`, `app`, `servicio`, `datos`, `externo`, `nota` o `decision`. `conexiones` (hasta 80) `de` → `a`, con `texto` opcional (hasta 80) y `tipo`: `llamada`, `respuesta` (punteada), `error` (roja) o `datos`. `grupos` opcionales `{id, nombre, color}` con color `azul`, `verde`, `violeta`, `ambar`, `rosa`, `lima`, `gris` o `rojo`. `direccion` opcional (`horizontal` o `vertical`; si no, se elige sola según el espacio). `titulo` hasta 100, `resumen` hasta 300, hasta 6 `notas`.
- `secuencia`: `actores` (hasta 12, `id` corto) y pasos `de` → `a`; sin `a` es un evento del mismo actor. `tipo` del paso: `llamada`, `respuesta` (punteada), `evento` o `error` (rojo).
- `proceso`: pasos con `id`; `duracion`, `icono` y `decision` (`si`/`no` apuntan a ids de pasos) son opcionales.
- Límites de `secuencia` y `proceso`: hasta 60 pasos; `texto` 120 caracteres, `detalle` 400, `datos` 160, `titulo` 100, `resumen` 300, hasta 6 `notas`.
- Todo es texto plano. El JSON tiene que ser válido (si no, la app lo muestra como código). Un bloque por diagrama; si hay varios en el mensaje, se muestran todos en orden.
