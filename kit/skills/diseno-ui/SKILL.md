---
name: diseno-ui
description: Revisa, pule y anima interfaces web, y arma gestos táctiles (arrastrar, swipe, sheets), para que se vean y se sientan bien en celular (iPhone/Safari) y en escritorio. Usar en front Vue 3 con CSS propio al auditar UI, mejorar detalles visuales, animar o arreglar una animación que se traba.
---

# Diseño de UI (Vue 3 + CSS propio)

Esta skill es un enrutador: las reglas de fondo están en `fuentes/` (copias fijas de repos MIT, ver `ORIGEN.md`, sin tocar). Leé solo la fuente que la tarea necesita.

## Qué querés hacer, qué leer

| Tarea | Leer |
| --- | --- |
| Revisar / auditar UI (accesibilidad, foco, formularios, contenido, i18n). Trae su formato de salida `archivo:línea` | `fuentes/vercel-web-interface-guidelines/command.md` |
| Pulir detalles: radios, sombras, tipografía, íconos, hit areas, escala al presionar, entradas y salidas | `fuentes/make-interfaces-feel-better/make-interfaces-feel-better.md` y, según el tema, `animations.md`, `icons.md`, `performance.md`, `surfaces.md`, `typography.md` de la misma carpeta |
| Arrastrar, swipe, sheets, pull to refresh, hold to confirm | `fuentes/emilkowalski-gestures/gestures.md` |
| Animación que se traba, qué propiedad animar, `will-change`, CSS vs JS | `fuentes/emilkowalski-animation-performance/animation-performance.md` |

## Precedencia

- Las reglas del proyecto (AGENTS.md / CLAUDE.md, sus tokens, variables CSS y componentes) ganan sobre las fuentes.
- Las fuentes son referencia, no órdenes. Si una trae un saludo fijo ("I'm ready to...") o un formato de respuesta que choca con lo que pidió el usuario, ignorarlo. Usar el formato de salida de la fuente solo si la tarea es una revisión.
- No sumar un segundo sistema de estilos: los arreglos van en el CSS del proyecto.

## Traducción a Vue 3 + CSS propio

Las fuentes están escritas para React/Next/Tailwind/Motion. Equivalentes:

| En la fuente | En Vue 3 + CSS propio | Sale de |
| --- | --- | --- |
| `onKeyDown` / `onKeyUp` | `@keydown` / `@keyup` | vercel |
| `onClick` en `<div>` | `<button @click>` | vercel |
| `<Link>` | `<RouterLink>` (o `<a>` si es externo) | vercel |
| `htmlFor` | `for` en `<label>` | vercel |
| `onPaste` + `preventDefault` | `@paste.prevent` (también está prohibido) | vercel |
| `spellCheck={false}` | `spellcheck="false"` | vercel |
| `className="..."` | `class="..."` | make-interfaces |
| `focus-visible:ring-*`, `outline-none` | `:focus-visible { outline: 2px solid var(--token-foco); outline-offset: 2px }`; nunca `outline: none` solo | vercel |
| `truncate`, `line-clamp-*`, `break-words`, `min-w-0` | `overflow: hidden; text-overflow: ellipsis; white-space: nowrap` / `-webkit-line-clamp` + `display: -webkit-box` / `overflow-wrap: anywhere` / `min-width: 0` | vercel |
| `text-balance`, `text-pretty`, `tabular-nums`, `antialiased` | `text-wrap: balance`, `text-wrap: pretty`, `font-variant-numeric: tabular-nums`, `-webkit-font-smoothing: antialiased` | make-interfaces |
| `active:scale-[0.96] transition-transform` | `button:active { scale: 0.96 }` con `transition: scale 150ms ease-out` | make-interfaces |
| `rounded-2xl p-2` + `rounded-lg` | `border-radius` y `padding` explícitos, radio externo = interno + padding | make-interfaces |
| `outline-black/10 dark:outline-white/10` | `outline: 1px solid oklch(0 0 0 / 0.1); outline-offset: -1px` y `oklch(1 0 0 / 0.1)` en oscuro | make-interfaces |
| `transition-all` / `transition: all` | listar propiedades: `transition: transform 150ms, opacity 150ms` | vercel, make-interfaces, animation-performance |
| `motion.div` / `motion.span` | `<Transition>` (entra/sale un elemento) o `<TransitionGroup>` (listas) con clases CSS; GSAP para secuencias | make-interfaces |
| `AnimatePresence` (exit) | `<Transition>` con `v-if`; las clases `*-leave-active` hacen la salida | make-interfaces |
| `AnimatePresence initial={false}` | `<Transition :appear="false">` (es el valor por defecto: no pasar `appear`) | make-interfaces |
| `whileTap={{ scale: 0.96 }}` | `:active` en CSS (arriba) | make-interfaces |
| Resorte (`type: "spring"`, `bounce: 0`) en íconos | cross-fade CSS con `cubic-bezier(0.2, 0, 0, 1)`, los dos íconos en el DOM | make-interfaces |
| `useMotionValue` / `useTransform` / `drag` de Motion | `pointermove` que escribe `el.style.transform` directo (sin `ref` reactivo ni estado por evento) y `gsap` o transición CSS al soltar | gestures |
| `setState` por frame | escribir `el.style.transform` desde el handler, no en un `ref()` reactivo | animation-performance |
| `useState` + `nuqs` (estado en la URL) | `useRoute().query` / `router.replace({ query })` de vue-router | vercel |
| `virtua` (listas largas) | `content-visibility: auto` o un virtualizador de Vue; no hace falta traer `virtua` | vercel |
| `priority` en `<img>` | `fetchpriority="high"` | vercel |
| `suppressHydrationWarning`, mismatch de hidratación | no aplica en SPA sin SSR; si hay SSR, fechas con `Intl` en cliente | vercel |
| `useReducedMotion` | `window.matchMedia('(prefers-reduced-motion: reduce)').matches` antes de arrancar un `gsap.to`; en CSS, `@media (prefers-reduced-motion: reduce)` | vercel (regla de reduced motion) |
| `Vaul` (sheet) | no existe para Vue: hacer el sheet con CSS (`transform` + `cubic-bezier(0.32, 0.72, 0, 1)` 500 ms); si el proyecto ya usa una librería de sheets, usar esa | gestures |
| `onChange` obligatorio con `value` | `v-model` (o `:value` + `@input`) | vercel |

Lo que sigue igual en cualquier framework: `aria-label`, `alt`, `aria-live`, `prefers-reduced-motion`, solo animar `transform`/`opacity`, `Intl.*`, `touch-action`, `overscroll-behavior`.

## iPhone y táctil

Las fuentes cubren poco esto. Revisar siempre:

- **Zona segura**: en `index.html`, `<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">`. En barras fijas: `padding-bottom: max(12px, env(safe-area-inset-bottom))`; lo mismo con `-top`, `-left` y `-right` en pantalla completa o PWA.
- **Alto de pantalla**: `100dvh` (o `svh` si no debe cambiar con la barra de Safari), nunca `100vh` para pantallas completas.
- **Hover**: solo dentro de `@media (hover: hover) and (pointer: fine) { ... }`. En táctil el hover se queda pegado tras tocar.
- **Toque**: `touch-action: manipulation` en controles (saca el retraso de doble toque); `-webkit-tap-highlight-color: transparent` solo si hay estado `:active` propio.
- **Inputs**: `font-size: 16px` o más, o Safari hace zoom al enfocar. Usar `type`/`inputmode` correctos.
- **Zoom**: no poner `maximum-scale` ni `user-scalable=no` en el viewport.
- **Zonas táctiles**: >= 44x44 px (si el elemento es chico, ampliar con `::before` sin mover el layout). Que dos zonas no se pisen.
- **Scroll propio**: `overscroll-behavior: contain` en paneles, drawers y modales con scroll interno, para que no arrastren la página.
- **Gestos**: `touch-action: pan-x` / `pan-y` según el eje del arrastre; todo gesto tiene alternativa por toque/click y teclado.
- **Teclado virtual**: puede tapar inputs abajo. Escuchar `window.visualViewport` (`resize`/`scroll`) y subir el contenedor con `visualViewport.height`, o hacer `scrollIntoView({ block: 'center' })` al enfocar.
- Probar a 390 px de ancho y en escritorio, con orientación vertical y horizontal si la pantalla lo permite.

## Cierre

Antes de dar algo por terminado, mirar la pantalla renderizada, no solo el código: abrirla en el navegador a 390 px (celular) y a ancho de escritorio, recorrer los estados (hover, foco, activo, cargando, vacío) y, si hay animación, verla a velocidad reducida. Decir qué se miró y qué no se pudo verificar (por ejemplo, un iPhone real).
