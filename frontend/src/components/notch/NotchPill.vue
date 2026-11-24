<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  altoMax,
  anchoPara,
  anchoVentanaFijo,
  CASCADA_S,
  cuerpoVisible,
  morph,
  pillAbierto,
  RADIO_ABIERTO,
  RADIO_CERRADO,
  superaUmbral,
  tamanoAlCambiarFoco,
  type ModoNotch,
} from '../../lib/notchMovimiento'
import {
  ajustarFormaAVentana,
  encogerFormaAPixeles,
  rectDestinoCentrado,
  rectFormaDesdeCaja,
} from '../../lib/notchFormaPastilla'
import { formaPara, type RectPastillaForma, pasosVentana, ventanaPara } from '../../lib/notchPuente'
import { esCampoTextoNotch } from '../../lib/notchTeclado'
import { puente } from '../../state/notch'
import { gsap, isSoft } from '../../motion'

const props = defineProps<{ modo: ModoNotch; foco: boolean; brillo?: string | null; pendientes?: number; escuchando?: boolean }>()
const emit = defineEmits<{ alternar: [] }>()

const pill = ref<HTMLElement | null>(null)
const cara = ref<HTMLElement | null>(null)
const cuerpo = ref<HTMLElement | null>(null)
const caraInner = ref<HTMLElement | null>(null)
const cerrando = ref(false)

let ro: ResizeObserver | undefined
let hoverTween: gsap.core.Tween | null = null
let punteroInicio: { x: number; y: number } | null = null
let arrastrado = false
let arrastreIniciado = false
let ultimoVentana: { ancho: number; alto: number } | null = null

function radioActualDePastilla(el: HTMLElement): number {
  const br = getComputedStyle(el).borderTopLeftRadius
  const n = parseFloat(br)
  return Number.isFinite(n) ? n : RADIO_CERRADO
}

function rectPastillaEnVentana(el: HTMLElement, w: number, h: number, radio: number): RectPastillaForma {
  const r = el.getBoundingClientRect()
  return rectFormaDesdeCaja(r, w, h, radio, window.scrollX, window.scrollY)
}

function rectPastillaDesdeDom(el: HTMLElement, radio: number): RectPastillaForma | null {
  const r = el.getBoundingClientRect()
  if (r.width <= 0 || r.height <= 0) return null
  return rectFormaDesdeCaja(r, r.width, r.height, radio, window.scrollX, window.scrollY)
}

/** Diferencia entre ancho dibujado y ancho CSS (content-box + borde, subpíxeles). */
function extraAnchoRenderPastilla(el: HTMLElement): number {
  const r = el.getBoundingClientRect()
  const cssW = parseFloat(getComputedStyle(el).width)
  if (!Number.isFinite(cssW)) return 0
  return Math.max(0, r.width - cssW)
}

function informarForma(rect: RectPastillaForma) {
  const dpr = window.devicePixelRatio || 1
  const r = encogerFormaAPixeles(ajustarFormaAVentana(rect), dpr)
  puente().forma(r.x, r.y, r.ancho, r.alto, r.radio)
}

function medidas() {
  const caraEl = cara.value
  const inner = caraInner.value
  const cuerpoEl = cuerpo.value
  if (!caraEl || !inner) return null
  const pantallaW = window.screen.availWidth
  const pantallaH = window.screen.availHeight
  const caraW = inner.offsetWidth
  const caraH = inner.offsetHeight
  const abierto = props.modo !== 'cerrado'
  const cuerpoH = abierto && cuerpoEl ? cuerpoEl.scrollHeight : 0
  const ancho = anchoPara(props.modo, caraW, pantallaW)
  const bodyPad = abierto ? 12 : 0
  let alto = caraH + cuerpoH + bodyPad
  const max = altoMax(pantallaH)
  if (alto > max) alto = max
  return { ancho, alto, caraH, max, abierto, cuerpoEl }
}

function renglonesCuerpo(): HTMLElement[] {
  const el = cuerpo.value
  return el ? ([...el.children] as HTMLElement[]) : []
}

function prepararRenglonesOcultos() {
  if (isSoft()) return
  const kids = renglonesCuerpo()
  if (!kids.length) return
  gsap.killTweensOf(kids)
  gsap.set(kids, { y: -10, opacity: 0 })
}

function limpiarRenglones() {
  const kids = renglonesCuerpo()
  if (!kids.length) return
  gsap.killTweensOf(kids)
  gsap.set(kids, { clearProps: 'opacity,y' })
}

function fadeOutRenglones() {
  if (isSoft()) return
  const kids = renglonesCuerpo()
  if (!kids.length) return
  gsap.killTweensOf(kids)
  gsap.to(kids, { opacity: 0, duration: 0.15, ease: 'power2.in' })
}

function cascada() {
  if (!cuerpo.value || props.modo === 'cerrado' || isSoft()) return
  const kids = renglonesCuerpo()
  if (!kids.length) return
  gsap.killTweensOf(kids)
  gsap.fromTo(
    kids,
    { y: -10, opacity: 0 },
    {
      y: 0,
      opacity: 1,
      duration: 0.45,
      stagger: CASCADA_S,
      delay: 0.12,
      ease: 'power2.out',
    },
  )
}

function cancelarCierreEnCurso() {
  if (!cerrando.value) return
  if (pill.value) gsap.killTweensOf(pill.value)
  const kids = renglonesCuerpo()
  if (kids.length) gsap.killTweensOf(kids)
  cerrando.value = false
  limpiarRenglones()
}

function aplicar(animarRenglones: boolean) {
  const m = medidas()
  if (!m || !pill.value) return
  const { ancho, alto, caraH, max, abierto, cuerpoEl } = m
  if (cuerpoEl && abierto) {
    const scrollMax = max - caraH - 12
    cuerpoEl.style.maxHeight = scrollMax > 0 ? `${scrollMax}px` : ''
  } else if (cuerpoEl) {
    cuerpoEl.style.maxHeight = ''
  }

  const anchoVentana = anchoVentanaFijo(window.screen.availWidth)
  const destino = ventanaPara({ ancho: anchoVentana, alto })
  const { antes, despues } = pasosVentana(ultimoVentana, destino)
  const pedirTamano = (v: { ancho: number; alto: number }) => {
    puente().tamano(v.ancho, v.alto, props.foco)
    ultimoVentana = v
  }
  const { duration, ease } = morph(isSoft())
  const radio = props.modo === 'cerrado' ? RADIO_CERRADO : RADIO_ABIERTO
  const extra = extraAnchoRenderPastilla(pill.value)
  const destRect = rectDestinoCentrado(
    window.innerWidth,
    ancho,
    alto,
    radio,
    extra,
    window.scrollX,
    window.scrollY,
  )

  if (isSoft()) {
    if (antes) pedirTamano(antes)
    gsap.set(pill.value, { width: ancho, height: alto, borderRadius: radio })
    if (despues) pedirTamano(despues)
    informarForma(destRect)
    if (animarRenglones) cascada()
    return
  }

  if (animarRenglones) {
    prepararRenglonesOcultos()
    cascada()
  }

  if (antes) pedirTamano(antes)
  const el = pill.value
  const cur = rectPastillaDesdeDom(el, radioActualDePastilla(el))
  informarForma(formaPara(destRect, cur ?? destRect))
  gsap.to(pill.value, {
    width: ancho,
    height: alto,
    borderRadius: radio,
    duration,
    ease,
    overwrite: 'auto',
    onComplete: () => {
      if (despues) pedirTamano(despues)
      void nextTick(() => informarForma(rectPastillaEnVentana(el, ancho, alto, radio)))
    },
  })
}

function aplicarCierre() {
  const m = medidas()
  if (!m || !pill.value) return
  const { ancho, alto, cuerpoEl } = m
  if (cuerpoEl) cuerpoEl.style.maxHeight = ''

  const anchoVentana = anchoVentanaFijo(window.screen.availWidth)
  const destino = ventanaPara({ ancho: anchoVentana, alto })
  const { antes, despues } = pasosVentana(ultimoVentana, destino)
  const pedirTamano = (v: { ancho: number; alto: number }) => {
    puente().tamano(v.ancho, v.alto, props.foco)
    ultimoVentana = v
  }
  const { duration, ease } = morph(isSoft())
  const radio = RADIO_CERRADO
  const extra = extraAnchoRenderPastilla(pill.value)
  const destRect = rectDestinoCentrado(
    window.innerWidth,
    ancho,
    alto,
    radio,
    extra,
    window.scrollX,
    window.scrollY,
  )

  fadeOutRenglones()

  if (isSoft()) {
    if (antes) pedirTamano(antes)
    gsap.set(pill.value, { width: ancho, height: alto, borderRadius: radio })
    if (despues) pedirTamano(despues)
    informarForma(destRect)
    cerrando.value = false
    limpiarRenglones()
    return
  }

  if (antes) pedirTamano(antes)
  const el = pill.value
  const cur = rectPastillaDesdeDom(el, radioActualDePastilla(el))
  informarForma(formaPara(destRect, cur ?? destRect))
  gsap.to(pill.value, {
    width: ancho,
    height: alto,
    borderRadius: radio,
    duration,
    ease,
    overwrite: 'auto',
    onComplete: () => {
      if (despues) pedirTamano(despues)
      void nextTick(() => {
        informarForma(rectPastillaEnVentana(el, ancho, alto, radio))
        cerrando.value = false
        limpiarRenglones()
      })
    },
  })
}

function ajustarTamano() {
  void nextTick(() => (cerrando.value ? aplicarCierre() : aplicar(false)))
}

function sync(prev: ModoNotch | undefined) {
  const abriendo = prev !== undefined && prev === 'cerrado' && props.modo !== 'cerrado'
  const cerrandoModo = prev !== undefined && prev !== 'cerrado' && props.modo === 'cerrado'

  if (cerrandoModo) {
    if (isSoft()) {
      void nextTick(() => aplicar(false))
      return
    }
    cerrando.value = true
    void nextTick(() => aplicarCierre())
    return
  }

  if (abriendo) cancelarCierreEnCurso()

  void nextTick(() => aplicar(abriendo))
}

onMounted(() => {
  if (pill.value) gsap.set(pill.value, { xPercent: -50 })
  sync(undefined)
  window.addEventListener('resize', ajustarTamano)
  ro = new ResizeObserver(() => ajustarTamano())
  if (caraInner.value) ro.observe(caraInner.value)
  if (cuerpo.value) ro.observe(cuerpo.value)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', ajustarTamano)
  ro?.disconnect()
  hoverTween?.kill()
})

watch(
  () => props.modo,
  (m, prev) => sync(prev),
)

watch(
  () => props.foco,
  (foco) => {
    const pedido = tamanoAlCambiarFoco(ultimoVentana, foco)
    if (pedido) puente().tamano(pedido.ancho, pedido.alto, pedido.foco)
  },
)

function onAlternar() {
  if (arrastrado) {
    arrastrado = false
    return
  }
  emit('alternar')
}

function onFacePointerDown(e: PointerEvent) {
  arrastrado = false
  if (!puente().enPrograma || e.button !== 0) return
  punteroInicio = { x: e.clientX, y: e.clientY }
  arrastreIniciado = false
}

function onFacePointerMove(e: PointerEvent) {
  if (!punteroInicio || arrastreIniciado) return
  const dx = e.clientX - punteroInicio.x
  const dy = e.clientY - punteroInicio.y
  if (!superaUmbral(dx, dy)) return
  arrastreIniciado = true
  arrastrado = true
  puente().arrastrar()
}

function onFacePointerUp() {
  punteroInicio = null
}

function onFacePointerCancel() {
  punteroInicio = null
}

function onEnter(e: KeyboardEvent) {
  if (e.key !== 'Enter' && e.key !== ' ') return
  if (esCampoTextoNotch(e.target)) return
  e.preventDefault()
  onAlternar()
}

function onHoverIn() {
  if (isSoft() || !caraInner.value) return
  hoverTween?.kill()
  hoverTween = gsap.to(caraInner.value, { scale: 1.04, duration: 0.35, ease: 'back.out(2.2)' })
}

function onHoverOut() {
  if (isSoft() || !caraInner.value) return
  hoverTween?.kill()
  hoverTween = gsap.to(caraInner.value, { scale: 1, duration: 0.35, ease: 'power2.out' })
}
</script>

<template>
  <div ref="pill" class="pill" :class="{ abierto: pillAbierto(modo, cerrando) }">
    <Transition name="pill-brillo-fade">
      <div
        v-if="brillo"
        key="brillo"
        class="pill-brillo"
        :style="{ '--pill-brillo': brillo }"
        aria-hidden="true"
      />
    </Transition>
    <div ref="cara" class="cara">
      <button
        ref="caraInner"
        type="button"
        class="face"
        :aria-expanded="modo === 'panel'"
        aria-label="Colmena"
        @click="onAlternar"
        @pointerdown="onFacePointerDown"
        @pointermove="onFacePointerMove"
        @pointerup="onFacePointerUp"
        @pointercancel="onFacePointerCancel"
        @keydown="onEnter"
        @mouseenter="onHoverIn"
        @mouseleave="onHoverOut"
      >
        <slot name="cara" />
        <span v-if="escuchando" class="escucha loop" role="img" aria-label="Escuchando una reunión" />
        <span v-if="(pendientes ?? 0) > 0" class="insignia" :aria-label="`${pendientes} para hacer`">{{ pendientes }}</span>
      </button>
    </div>
    <div v-show="cuerpoVisible(modo, cerrando)" ref="cuerpo" class="cuerpo">
      <slot name="cuerpo" />
    </div>
  </div>
</template>

<style scoped>
.pill {
  position: fixed;
  top: 0;
  left: 50%;
  z-index: 50;
  isolation: isolate;
  color-scheme: dark;
  background: var(--bg-2);
  border: 1px solid color-mix(in srgb, var(--text) 11%, transparent);
  overflow: hidden;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.04);
}
.pill-brillo {
  position: absolute;
  inset: 0;
  z-index: -1;
  pointer-events: none;
  background: radial-gradient(
    ellipse 260px 180px at 40px 30px,
    color-mix(in srgb, var(--pill-brillo) 15%, transparent),
    transparent 70%
  );
}
.pill-brillo-fade-enter-active,
.pill-brillo-fade-leave-active {
  transition: opacity 0.25s ease;
}
.pill-brillo-fade-enter-from,
.pill-brillo-fade-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .pill-brillo-fade-enter-active,
  .pill-brillo-fade-leave-active {
    transition: none;
  }
}
.cara {
  position: relative;
  z-index: 0;
  width: 100%;
  display: flex;
  justify-content: center;
  box-sizing: border-box;
}
.face {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 16px 7px 9px;
  width: max-content;
  cursor: pointer;
  user-select: none;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
}
.escucha {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--miel);
  box-shadow: 0 0 0 3px var(--miel-soft);
  animation: escucha-late 1.8s ease-in-out infinite;
}
@keyframes escucha-late {
  50% {
    opacity: 0.45;
  }
}
@media (prefers-reduced-motion: reduce) {
  .escucha {
    animation: none;
  }
}
.insignia {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  box-sizing: border-box;
  border-radius: var(--r-pill);
  background: var(--miel);
  color: var(--accent-ink);
  font: 700 10px/18px var(--font-mono);
  text-align: center;
}
.face:focus-visible {
  outline: 1px solid color-mix(in srgb, var(--accent) 50%, transparent);
  outline-offset: -1px;
  border-radius: 20px;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent);
}
.cuerpo {
  position: relative;
  z-index: 0;
  padding: 2px 10px 10px;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
}
:root[data-theme='light'] .pill {
  color-scheme: light;
}
</style>
