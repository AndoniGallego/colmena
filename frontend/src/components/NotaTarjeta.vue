<script setup lang="ts">
import { computed, ref } from 'vue'
import type { Nota } from '../api/types'
import { corto } from '../lib/notas'
import { ago, useNow } from '../lib/time'
import { gsap, isSoft } from '../motion'

const props = defineProps<{ nota: Nota; seleccionada?: boolean; sesionViva: boolean; deslizable?: boolean }>()
const emit = defineEmits<{ abrir: []; completar: [hecha: boolean]; seleccionar: [] }>()

const now = useNow()
const recordatorio = computed(() => props.nota.tipo === 'recordatorio')
const hecha = computed(() => recordatorio.value && !!props.nota.hecha_at)
const clase = computed(() => (hecha.value ? 'hecha' : recordatorio.value ? 'todo' : 'apunte'))
const etiqueta = computed(() => (hecha.value ? 'Hecha' : recordatorio.value ? 'Para hacer' : 'Apunte'))
const irASesion = computed(() => (props.nota.origen?.nombre ? `Ir a la sesión ${props.nota.origen.nombre}` : 'Ir a la sesión de origen'))
const cuando = computed(() => ago(props.nota.creada_at, now.value))

// ---------- deslizar para completar (celu) ----------
// El movimiento se escribe directo en el estilo: no pasa por el estado reactivo en cada pointermove.
const raiz = ref<HTMLElement | null>(null)
const miel = ref<HTMLElement | null>(null)
const UMBRAL = 8
const RESISTENCIA = 0.3
let gesto: { id: number; x: number; y: number; ancho: number; tomado: boolean; dx: number } | null = null
let arrastro = false

const avance = (dx: number, ancho: number) => (dx <= 0 ? 0 : dx <= ancho ? dx : ancho + (dx - ancho) * RESISTENCIA)

function alPresionar(e: PointerEvent) {
  arrastro = false
  if (!props.deslizable || gesto?.tomado) return
  gesto = { id: e.pointerId, x: e.clientX, y: e.clientY, ancho: raiz.value?.getBoundingClientRect().width || 1, tomado: false, dx: 0 }
}
function alMover(e: PointerEvent) {
  const g = gesto
  const el = raiz.value
  if (!g || !el || e.pointerId !== g.id) return
  const dx = e.clientX - g.x
  const dy = e.clientY - g.y
  if (!g.tomado) {
    // Solo hacia la derecha y antes que el deslizar entre pestañas de la app (que arranca a los 9 px).
    if (dx > UMBRAL && dx > Math.abs(dy)) {
      g.tomado = true
      arrastro = true
      el.classList.add('arrastrando')
      gsap.killTweensOf(el)
      try {
        el.setPointerCapture?.(e.pointerId)
      } catch {
        // sin captura el gesto sigue mientras el dedo esté sobre la tarjeta
      }
    } else {
      if (Math.abs(dy) > UMBRAL || dx < -UMBRAL) gesto = null
      return
    }
  }
  // El gesto es de la tarjeta: que no le llegue al deslizar entre pestañas.
  e.stopPropagation()
  g.dx = dx
  el.style.transform = `translateX(${avance(dx, g.ancho)}px)`
  if (miel.value) miel.value.style.transform = `scaleX(${Math.min(1, Math.max(0, dx / g.ancho))})`
}
function alSoltar(e: PointerEvent) {
  const g = gesto
  const el = raiz.value
  if (!g || e.pointerId !== g.id) return
  gesto = null
  if (!g.tomado || !el) return
  e.stopPropagation()
  try {
    el.releasePointerCapture?.(e.pointerId)
  } catch {
    // ya soltada
  }
  const completa = e.type === 'pointerup' && g.dx >= g.ancho / 2
  if (completa) {
    el.classList.remove('arrastrando')
    el.style.transform = ''
    if (miel.value) gsap.to(miel.value, { opacity: 0, duration: 0.15, onComplete: () => miel.value && (miel.value.style.cssText = '') })
    emit('completar', true)
    return
  }
  gsap.to(el, {
    x: 0,
    duration: 0.25,
    ease: isSoft() ? 'power2.out' : 'back.out(1.4)',
    clearProps: 'transform',
    onComplete: () => el.classList.remove('arrastrando'),
  })
  if (miel.value) gsap.to(miel.value, { scaleX: 0, duration: 0.25, ease: 'power2.out', clearProps: 'transform' })
}
// Un arrastre no debe contar como toque: el click que sigue a soltar no abre la hoja.
function alClick(e: MouseEvent) {
  if (!arrastro) return
  arrastro = false
  e.stopPropagation()
  e.preventDefault()
}
</script>

<template>
  <article
    ref="raiz"
    class="nota"
    :class="[`k-${clase}`, { sel: seleccionada, deslizable }]"
    :data-id="nota.id"
    @pointerdown="alPresionar"
    @pointermove="alMover"
    @pointerup="alSoltar"
    @pointercancel="alSoltar"
    @click.capture="alClick"
  >
    <span class="nota-ala l" aria-hidden="true" />
    <span class="nota-ala r" aria-hidden="true" />
    <span class="nota-sombra" aria-hidden="true" />
    <div class="nota-in">
      <span class="nota-miel" aria-hidden="true" />
      <span ref="miel" class="nota-deslizar" aria-hidden="true" />
      <span class="nota-brillo" aria-hidden="true" />
      <button type="button" class="nota-abrir" :aria-label="`${etiqueta}: ${corto(nota.texto)}`" :aria-pressed="!!seleccionada" @click="emit('seleccionar')" />
      <div class="nota-cuerpo">
        <span class="nota-tipo">{{ etiqueta }}</span>
        <span class="nota-texto">{{ nota.texto }}</span>
      </div>
      <button
        v-if="recordatorio"
        type="button"
        class="nota-tilde hit"
        :aria-label="hecha ? 'Volver a pendiente' : 'Marcar hecha'"
        :aria-pressed="hecha"
        @click="emit('completar', !hecha)"
      >
        <svg viewBox="0 0 24 24" aria-hidden="true">
          <path class="hexo" d="M12 2 21 7v10l-9 5-9-5V7z" />
          <g class="nota-tilde-marca"><path class="tick" d="M7.5 12.5l3 3 6-6.5" /></g>
        </svg>
      </button>
      <i v-else class="nota-sello" aria-hidden="true" />
      <div class="nota-pie">
        <button
          v-if="nota.origen"
          type="button"
          class="nota-origen hit"
          :disabled="!sesionViva"
          :aria-label="irASesion"
          :title="sesionViva ? irASesion : 'La sesión ya no está'"
          @click="emit('abrir')"
        >
          <span aria-hidden="true">↩</span><span class="nota-origen-n">{{ nota.origen.nombre }}</span>
        </button>
        <span v-else class="nota-suelta">idea suelta</span>
        <span v-if="nota.origen && !sesionViva" class="nota-ida">la sesión ya no está</span>
        <span v-else class="nota-cuando">{{ cuando }}</span>
      </div>
    </div>
  </article>
</template>

<style scoped>
.nota {
  position: relative;
  isolation: isolate;
  min-width: 0;
}
.nota-in {
  position: relative;
  z-index: 1;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 12px 10px 14px;
  border-radius: var(--r-lg);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  overflow: hidden;
}
.nota.sel .nota-in {
  box-shadow: inset 0 0 0 1.5px var(--accent), 0 10px 30px -18px var(--accent);
}
.nota:has(.nota-abrir:focus-visible) .nota-in {
  box-shadow: inset 0 0 0 2px var(--accent);
}

/* Toda la tarjeta abre el detalle; el texto va encima sin tomar toques y el tilde y el origen quedan arriba de todo. */
.nota-abrir {
  position: absolute;
  inset: 0;
  z-index: 1;
  outline: none;
  touch-action: manipulation;
}
.nota-cuerpo {
  position: relative;
  z-index: 2;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding-right: 30px;
  pointer-events: none;
}
.nota-tipo {
  font: 600 var(--t-2xs) / 1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-3);
}
.nota-texto {
  font: 600 var(--t-lg) / 1.3 var(--font-display);
  color: var(--text);
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  overflow: hidden;
}

/* Sello hexagonal: lima el apunte, contorno el recordatorio, miel la hecha. */
.nota-sello {
  position: absolute;
  top: 13px;
  right: 13px;
  z-index: 3;
  width: 14px;
  height: 16px;
  background: var(--accent);
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
}
.nota-tilde {
  position: absolute;
  top: 5px;
  right: 5px;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-sm);
  color: var(--text-3);
  touch-action: manipulation;
}
.nota-tilde svg {
  width: 22px;
  height: 22px;
  overflow: visible;
  transition: transform 0.35s var(--spring);
}
.nota-tilde .hexo {
  fill: transparent;
  stroke: currentColor;
  stroke-width: 1.6;
}
.nota-tilde .tick {
  fill: none;
  stroke: var(--bg);
  stroke-width: 2.6;
  stroke-linecap: round;
  stroke-linejoin: round;
}
.nota-tilde-marca {
  clip-path: inset(0% 100% 0% 0%);
}
.nota-tilde:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.nota-tilde:active svg {
  transform: scale(var(--press-scale));
}

.nota-pie {
  position: relative;
  z-index: 2;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  min-width: 0;
  font: 500 var(--t-2xs) / 1 var(--font-mono);
  color: var(--text-3);
  pointer-events: none;
}
.nota-origen {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  max-width: 100%;
  flex: 0 1 auto;
  min-height: 24px;
  padding: 0 9px;
  border-radius: var(--r-pill);
  font: inherit;
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent-line);
  pointer-events: auto;
  touch-action: manipulation;
}
.nota-origen-n {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nota-origen:disabled {
  color: var(--text-4);
  box-shadow: inset 0 0 0 1px var(--line-2);
  cursor: not-allowed;
}
.nota-origen:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
/* Si no entran en una línea, el pie baja a dos en vez de cortar el nombre a unas letras. */
.nota-suelta,
.nota-cuando,
.nota-ida {
  white-space: nowrap;
}
.nota-cuando,
.nota-ida {
  margin-left: auto;
}
.nota-cuando {
  flex: none;
}
.nota-ida {
  flex: none;
  color: var(--text-4);
}

/* Hecha: la celda quedó llena de miel. */
.nota.k-hecha .nota-in {
  background: linear-gradient(to top, color-mix(in srgb, var(--miel) 28%, var(--surface-2)), color-mix(in srgb, var(--miel) 7%, var(--surface-2)));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--miel) 35%, transparent);
}
.nota.k-hecha.sel .nota-in {
  box-shadow: inset 0 0 0 1.5px var(--miel), 0 10px 30px -18px var(--miel);
}
.nota.k-hecha .nota-texto {
  color: var(--text-2);
  text-decoration: line-through;
  text-decoration-color: color-mix(in srgb, var(--miel) 60%, transparent);
}
.nota.k-hecha .nota-tipo {
  color: var(--miel);
}
.nota.k-hecha .nota-tilde .hexo {
  fill: var(--miel);
  stroke: var(--miel);
}
.nota.k-hecha .nota-tilde-marca {
  clip-path: inset(0% 0% 0% 0%);
}

/* Sombra que aparece al levantar la tarjeta con el dedo (se anima solo la opacidad). */
.nota-sombra {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: var(--r-lg);
  box-shadow: 0 12px 26px -8px rgba(0, 0, 0, 0.55);
  opacity: 0;
  pointer-events: none;
}

/* Deslizar para completar: la miel crece de izquierda a derecha detrás del texto. */
.nota.deslizable {
  touch-action: pan-y;
}
/* Mientras se arrastra pasa por encima de la tarjeta vecina. */
.nota.arrastrando {
  z-index: 3;
}
.nota-deslizar {
  position: absolute;
  inset: 0;
  z-index: 0;
  background: linear-gradient(to right, var(--miel-soft), color-mix(in srgb, var(--miel) 55%, transparent));
  transform: scaleX(0);
  transform-origin: 0 50%;
  pointer-events: none;
}

/* Piezas de la animación de completar (lib/notasMovimiento). */
.nota-miel {
  position: absolute;
  left: -50%;
  top: 104%;
  width: 200%;
  aspect-ratio: 1;
  border-radius: 42%;
  background: var(--miel);
  z-index: 0;
  pointer-events: none;
}
.nota-brillo {
  position: absolute;
  inset: 0;
  z-index: 0;
  border-radius: inherit;
  box-shadow: inset 0 0 0 1.5px var(--accent), inset 0 0 24px -8px var(--accent);
  opacity: 0;
  pointer-events: none;
}
.nota-ala {
  position: absolute;
  top: 4%;
  width: 46%;
  height: 34%;
  border-radius: 50%;
  background: radial-gradient(ellipse at 50% 60%, color-mix(in srgb, var(--text) 55%, transparent), color-mix(in srgb, var(--text) 8%, transparent) 70%);
  border: 1px solid color-mix(in srgb, var(--text) 35%, transparent);
  opacity: 0;
  z-index: 0;
  pointer-events: none;
}
.nota-ala.l {
  left: -22%;
  transform-origin: 100% 80%;
  rotate: -28deg;
}
.nota-ala.r {
  right: -22%;
  transform-origin: 0% 80%;
  rotate: 28deg;
}
.nota.melada .nota-texto,
.nota.melada .nota-tipo,
.nota.melada .nota-pie {
  color: var(--bg);
}
.nota.melada .nota-tilde .hexo {
  stroke: var(--bg);
  fill: color-mix(in srgb, var(--bg) 12%, transparent);
}

@media (hover: hover) and (pointer: fine) {
  .nota:not(.sel):hover .nota-in {
    box-shadow: inset 0 0 0 1px var(--accent-line);
  }
  .nota-tilde:hover {
    color: var(--miel);
  }
  .nota-tilde:hover svg {
    transform: rotate(30deg);
  }
  .nota-origen:not(:disabled):hover {
    background: var(--accent-soft);
  }
}
@media (pointer: coarse) {
  .nota-tilde {
    width: 44px;
    height: 44px;
    top: 0;
    right: 0;
  }
  .nota-cuerpo {
    padding-right: 36px;
  }
}
:root[data-motion='soft'] .nota-tilde svg {
  transition: none;
}
</style>
