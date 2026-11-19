<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { desktop } from '../lib/viewport'
import { ago, useNow } from '../lib/time'
import { animateViewEnter, gsap, haptic, isSoft, useGsap } from '../motion'
import ViewFrame from './ViewFrame.vue'
import { mrsAutoSelectRef } from '../lib/mrsAutoSelect'
import InlineAlert from './InlineAlert.vue'
import EmptyState from './EmptyState.vue'
import SkeletonList from './SkeletonList.vue'
import { abrirMr, cargarMrs, cerrarMr, crearRequest, cuenta, enPausa, mrs, visibles } from '../state/mrs'
import Icon from './Icon.vue'
import MrCard from './MrCard.vue'
import MrPausados from './MrPausados.vue'
import MrCreateSheet from './MrCreateSheet.vue'
import MrDetail from './MrDetail.vue'
import MrPinSheet from './MrPinSheet.vue'
import SegControl from './SegControl.vue'
import { openSessionId } from '../state/session'

const props = defineProps<{ visible: boolean }>()
const { run } = useGsap()
const now = useNow()
const scroller = ref<HTMLElement | null>(null)
const crear = ref(false)
const crearSesion = ref<string | null>(null)
function nuevo(sessionId: string | null = null) {
  haptic(5)
  crearSesion.value = sessionId ?? openSessionId.value
  crear.value = true
}
watch(crearRequest, (r) => r && nuevo(r.sessionId))

const filtros = computed(() => [
  { value: 'todos' as const, label: `Todos · ${visibles.value.length}` },
  { value: 'autor' as const, label: `Míos · ${cuenta.value.autor}` },
  { value: 'revisor' as const, label: `A revisar · ${cuenta.value.revisor}` },
])
const pausaAbierta = ref(false)
watch(() => enPausa.value.length, (n) => n || (pausaAbierta.value = false))
const vacioMsg = computed(() => {
  if (enPausa.value.length && !visibles.value.length) return 'Todo lo demás está en pausa.'
  if (mrs.filtro === 'revisor') return 'Nadie te pidió revisar nada.'
  if (mrs.filtro === 'autor') return 'No tenés MRs abiertos.'
  return 'No hay MRs abiertos tuyos ni para revisar.'
})
const actualizado = computed(() => (mrs.actualizado ? ago(new Date(mrs.actualizado * 1000).toISOString(), now.value) : ''))

function abrir(ref: string) {
  haptic(5)
  abrirMr(ref)
}
function refrescar() {
  if (mrs.refreshing) return
  haptic(6)
  void cargarMrs(false, true)
}

const pullInd = ref<HTMLElement | null>(null)
let pullDist = 0
let startY: number | null = null
function writePull(p: number, soltar = false) {
  const el = pullInd.value
  if (!el) return
  el.style.transition = soltar && !isSoft() ? 'transform 0.25s var(--ease-out), opacity 0.25s var(--ease-out)' : ''
  el.style.transform = `translate(-50%, ${p - 28}px) rotate(${p * 4}deg)`
  el.style.opacity = String(Math.min(1, p / 60))
}
function onTouchStart(e: TouchEvent) {
  startY = scroller.value && scroller.value.scrollTop <= 0 ? e.touches[0].clientY : null
  pullDist = 0
  if (startY !== null) writePull(0)
}
function onTouchMove(e: TouchEvent) {
  if (startY === null) return
  const dy = e.touches[0].clientY - startY
  pullDist = dy > 0 ? Math.min(90, dy * 0.45) : 0
  writePull(pullDist)
}
function onTouchEnd() {
  if (startY !== null && pullDist >= 60) refrescar()
  startY = null
  pullDist = 0
  writePull(0, true)
}

watch(
  () => [mrs.loaded, mrs.filtro] as const,
  async ([loaded]) => {
    if (!loaded || isSoft() || !props.visible) return
    await nextTick()
    animateViewEnter(gsap, run, scroller.value?.querySelectorAll('.item'), isSoft())
  },
)

watch(
  () =>
    [
      props.visible,
      desktop.value,
      mrs.loaded,
      mrs.sel,
      visibles.value.map((m) => m.ref).join('\n'),
    ] as const,
  () => {
    if (!props.visible) return
    const ref = mrsAutoSelectRef({
      desktop: desktop.value,
      loaded: mrs.loaded,
      selected: mrs.sel,
      visibleRefs: visibles.value.map((m) => m.ref),
    })
    if (ref) abrirMr(ref)
  },
)

// Deslizar el detalle hacia la derecha vuelve a la lista (en la PWA de iPhone no hay gesto de volver del sistema).
const NOSWIPE = '.md-table, .md-code, .diff, textarea, input, select, [data-noswipe]'
const detEl = ref<HTMLElement | null>(null)
let sw: { id: number; x0: number; y0: number; lock: 'x' | 'y' | null; w: number; lx: number; lt: number; v: number } | null = null
function swDown(e: PointerEvent) {
  if (desktop.value || e.pointerType === 'mouse' || !detEl.value || !mrs.sel) return
  if ((e.target as Element).closest(NOSWIPE)) return
  sw = { id: e.pointerId, x0: e.clientX, y0: e.clientY, lock: null, w: detEl.value.clientWidth, lx: e.clientX, lt: e.timeStamp, v: 0 }
}
function swMove(e: PointerEvent) {
  if (!sw || e.pointerId !== sw.id || !detEl.value) return
  const dx = e.clientX - sw.x0
  const dy = e.clientY - sw.y0
  if (!sw.lock) {
    if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
    sw.lock = Math.abs(dx) > Math.abs(dy) * 1.4 && dx > 0 ? 'x' : 'y'
    if (sw.lock === 'x') detEl.value.setPointerCapture(e.pointerId)
  }
  if (sw.lock !== 'x') return
  const dt = Math.max(1, e.timeStamp - sw.lt)
  sw.v = (e.clientX - sw.lx) / dt
  sw.lx = e.clientX
  sw.lt = e.timeStamp
  gsap.set(detEl.value, { x: Math.max(0, dx) })
}
function swUp(e: PointerEvent) {
  const s = sw
  sw = null
  const el = detEl.value
  if (!s || !el || s.lock !== 'x') return
  const dx = Math.max(0, e.clientX - s.x0)
  const go = dx > s.w * 0.35 || s.v > 0.6
  if (isSoft()) {
    gsap.set(el, { x: 0 })
    if (go) cerrarMr()
    return
  }
  if (go) {
    haptic(8)
    gsap.to(el, { x: s.w, duration: 0.26, ease: 'power3.out', onComplete: cerrarMr })
  } else {
    gsap.to(el, { x: 0, duration: 0.25, ease: 'power3.out', clearProps: 'transform' })
  }
}

function detEnter(el: Element, done: () => void) {
  if (desktop.value) return done()
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.18, onComplete: done }))
  run(() => gsap.fromTo(el, { xPercent: 100 }, { xPercent: 0, duration: 0.5, ease: 'expo.out', clearProps: 'transform', onComplete: done }))
}
function detLeave(el: Element, done: () => void) {
  if (desktop.value) return done()
  if (gsap.getProperty(el, 'x') !== 0) return void run(() => gsap.to(el, { opacity: 0, duration: 0.12, onComplete: done }))
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
  run(() => gsap.to(el, { xPercent: 100, duration: 0.32, ease: 'power3.in', onComplete: done }))
}
</script>

<template>
  <ViewFrame
    split
    class="mrs"
    aria-label="Merge requests"
    title="MRs"
    :subtitle="actualizado ? `Actualizado ${actualizado}` : mrs.loaded ? '' : 'Leyendo GitLab…'"
  >
    <template #actions>
      <button type="button" class="btn btn-ghost btn-icon" :class="{ spinning: mrs.refreshing }" aria-label="Actualizar" :disabled="mrs.refreshing" @click="refrescar"><Icon name="refresh" :size="16" /></button>
      <button type="button" class="btn btn-primary" @click="nuevo()"><Icon name="plus" :size="16" /> Nuevo MR</button>
    </template>
    <template #toolbar>
      <SegControl v-model="mrs.filtro" class="seg" :options="filtros" label="Filtrar MRs" />
    </template>
    <template #aside>
      <div
        ref="scroller"
        class="aside-scroll"
        @touchstart.passive="onTouchStart"
        @touchmove.passive="onTouchMove"
        @touchend="onTouchEnd"
        @touchcancel="onTouchEnd"
      >
        <div class="pull" aria-hidden="true">
          <span ref="pullInd" class="pull-ind"><Icon name="refresh" :size="16" /></span>
        </div>

        <i v-if="mrs.refreshing" class="ui-refresh-bar" aria-hidden="true" />

        <InlineAlert v-if="!mrs.disponible" tone="soft">No encuentro glab en esta compu, así que no puedo leer GitLab.</InlineAlert>
        <InlineAlert v-else-if="mrs.error">
          {{ mrs.error }}
          <template #action><button type="button" class="btn btn-link" @click="refrescar">Reintentar</button></template>
        </InlineAlert>

        <SkeletonList v-if="!mrs.loaded && mrs.disponible && !mrs.error" />

        <ul class="items">
          <li v-for="m in visibles" :key="m.ref" class="item">
            <MrCard :m="m" :now="now" @open="abrir" />
          </li>
        </ul>

        <MrPausados v-model:open="pausaAbierta" :items="enPausa" :now="now" @open="abrir" />

        <EmptyState v-if="mrs.loaded && !visibles.length && !mrs.error" icon="merge">{{ vacioMsg }}</EmptyState>
      </div>
    </template>

    <Transition :css="false" @enter="detEnter" @leave="detLeave">
      <div v-if="mrs.sel || desktop" ref="detEl" class="det" @pointerdown="swDown" @pointermove="swMove" @pointerup="swUp" @pointercancel="swUp">
        <div class="det-in">
          <MrDetail v-if="mrs.sel" :key="mrs.sel" @back="cerrarMr" />
          <EmptyState v-else icon="merge">Elegí un MR para ver el pipeline, los hilos y los archivos.</EmptyState>
        </div>
      </div>
    </Transition>

    <MrPinSheet />
    <MrCreateSheet :open="crear" :session-id="crearSesion" @close="crear = false" />
  </ViewFrame>
</template>

<style scoped>
.mrs { position: relative; overflow: hidden; }
.mrs :deep(.vf-aside-scroll) {
  padding: 0;
  overflow: hidden;
  scrollbar-gutter: auto;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.aside-scroll {
  position: relative;
  flex: 1;
  min-height: 0;
  min-width: 0;
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  display: flex;
  flex-direction: column;
  gap: var(--view-body-gap);
  padding: var(--view-pad-top) var(--gutter-end) calc(16px + env(safe-area-inset-bottom)) var(--gutter);
  scrollbar-gutter: stable;
}
.pull { position: relative; height: 0; margin: -8px 0 0; color: var(--accent); }
.pull-ind { position: absolute; top: 0; left: 50%; display: grid; place-items: center; width: 28px; height: 28px; opacity: 0; transform: translate(-50%, -28px); will-change: transform; pointer-events: none; }
.items { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.seg { width: 100%; min-width: 0; }
.det { position: absolute; inset: 0; z-index: 3; min-height: 0; min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr); background: var(--bg); touch-action: pan-y; overscroll-behavior-x: none; }
.det-in {
  min-height: 0;
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  overflow: hidden;
}
.det .empty { align-self: center; }
@media (min-width: 1024px) {
  .det { position: relative; inset: auto; z-index: auto; background: transparent; }
  .pull { display: none; }
  .det-in { height: 100%; }
  .aside-scroll { padding-bottom: calc(24px + env(safe-area-inset-bottom)); }
}
</style>
