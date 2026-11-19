<script lang="ts">
export { corrimientoPx, deltaArrastreY, indicesCorrimientoArrastre } from '../lib/boardDrag'
export { destinoReordenQuieto } from '../lib/order'
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { boardState, highlight } from '../state/app'
import { Flip, gsap, isSoft, useGsap, vSpotlight } from '../motion'
import {
  aplicarOrdenManual,
  idDeWorkspace,
  destinoReordenQuieto,
  moverEnOrden,
  ordenTrasArrastreQuietos,
  sortWorkspaces,
  wsEsActivoParaOrden,
} from '../lib/order'
import { corrimientoPx, deltaArrastreY } from '../lib/boardDrag'
import {
  guardarOrden,
  guardarPlegadas,
  hayOrdenManual,
  ordenError,
  ordenGuardado,
  plegadasError,
  plegadasGuardado,
  volverOrdenAutomatico,
} from '../state/ordenTablero'
import { ago, useNow } from '../lib/time'
import WorkspaceCard, { type ReorderUi } from './WorkspaceCard.vue'
import { compartir } from '../lib/compartir'
import LimpiezaChip from './LimpiezaChip.vue'
import MudanzaChip from './MudanzaChip.vue'
import MudanzaSheet from './MudanzaSheet.vue'
import NuevaTerminalSheet from './NuevaTerminalSheet.vue'
import RetomarSesionSheet from './RetomarSesionSheet.vue'
import Icon from './Icon.vue'
import ViewFrame from './ViewFrame.vue'
import EmptyState from './EmptyState.vue'
import { iniciarMudanza } from '../state/mudanza'
import { haptic } from '../motion'

const nuevaAbierta = ref(false)
const nuevaGrupo = ref<string | undefined>(undefined)
function abrirNueva() {
  haptic(4)
  nuevaGrupo.value = undefined
  nuevaAbierta.value = true
}
function sumarPestana(grupoId: string) {
  haptic(4)
  nuevaGrupo.value = grupoId
  nuevaAbierta.value = true
}

const retomarAbierta = ref(false)
function abrirRetomar() {
  haptic(4)
  retomarAbierta.value = true
}

const now = useNow()
const board = computed(() => boardState.value.board)
const autoWorkspaces = computed(() => sortWorkspaces(board.value?.workspaces ?? []))
const workspaces = computed(() => aplicarOrdenManual(autoWorkspaces.value, ordenGuardado.value, idDeWorkspace))
const manualIds = computed(() => workspaces.value.map(idDeWorkspace))

const dragFrom = ref<number | null>(null)
const dragOver = ref<number | null>(null)
const gripArmed = ref(false)
const ROOT_DRAG = 'orq-arrastrando-tablero'
const GRIP_MS = 360
let gripHold: ReturnType<typeof setTimeout> | undefined
let gripStart: { index: number; id: number; el: HTMLElement } | null = null
let dragListeners: (() => void) | null = null
let scrollRaf = 0
let liftEl: HTMLElement | null = null
let liftStartY = 0
let liftStep = 0
let liftStartScroll = 0
let cardMids: number[] = []
let scrollerTop = 0
let scrollerBottom = 0
let lastShiftTo = -1
let lastClientY = 0
let scrollAcc = 0

function medirTarjetas() {
  const sc = scroller.value
  const base = sc?.scrollTop ?? 0
  const sr = sc?.getBoundingClientRect()
  scrollerTop = sr?.top ?? 0
  scrollerBottom = sr?.bottom ?? 0
  liftStartScroll = base
  cardMids = cards().map((c) => {
    const r = c.getBoundingClientRect()
    return r.top + base + r.height / 2
  })
}

function limpiarVisualArrastre() {
  if (liftEl) {
    gsap.killTweensOf(liftEl)
    liftEl.classList.remove('drag-float')
  }
  const els = cards()
  if (els.length) gsap.killTweensOf(els)
  gsap.set(els, { clearProps: 'transform,y,scale,boxShadow' })
  liftEl = null
  liftStep = 0
  cardMids = []
  lastShiftTo = -1
}

function actualizarVisualArrastre(clientY: number) {
  if (!liftEl || dragFrom.value === null || dragOver.value === null) return
  const scrolled = (scroller.value?.scrollTop ?? 0) - liftStartScroll
  gsap.set(liftEl, { y: deltaArrastreY(clientY, liftStartY) + scrolled, scale: 1.02, force3D: true })
  const to = dragOver.value
  if (to === lastShiftTo) return
  lastShiftTo = to
  const from = dragFrom.value
  const all = cards()
  for (let i = 0; i < all.length; i++) {
    const card = all[i]!
    if (card === liftEl) continue
    gsap.to(card, { y: corrimientoPx(from, to, i, liftStep), duration: 0.16, ease: 'power2.out', overwrite: 'auto' })
  }
}

function detachDrag() {
  dragListeners?.()
  dragListeners = null
  document.documentElement.classList.remove(ROOT_DRAG)
  gripStart = null
  gripArmed.value = false
  dragFrom.value = null
  dragOver.value = null
  if (scrollRaf) cancelAnimationFrame(scrollRaf)
  scrollRaf = 0
  limpiarVisualArrastre()
}

const BORDE_AUTOSCROLL = 56
const VEL_MAX_AUTOSCROLL = 14

function velocidadAutoScroll(clientY: number): number {
  if (clientY < scrollerTop + BORDE_AUTOSCROLL) {
    return -VEL_MAX_AUTOSCROLL * Math.min(1, (scrollerTop + BORDE_AUTOSCROLL - clientY) / BORDE_AUTOSCROLL)
  }
  if (clientY > scrollerBottom - BORDE_AUTOSCROLL) {
    return VEL_MAX_AUTOSCROLL * Math.min(1, (clientY - (scrollerBottom - BORDE_AUTOSCROLL)) / BORDE_AUTOSCROLL)
  }
  return 0
}

function autoScrollArrastre() {
  scrollRaf = 0
  const el = scroller.value
  if (!el || dragFrom.value === null) return
  const v = velocidadAutoScroll(lastClientY)
  if (v !== 0) {
    scrollAcc += v
    const step = Math.trunc(scrollAcc)
    if (step) {
      scrollAcc -= step
      const antes = el.scrollTop
      el.scrollTop += step
      if (el.scrollTop !== antes) seguirArrastre(lastClientY)
    }
  }
  scrollRaf = requestAnimationFrame(autoScrollArrastre)
}

function seguirArrastre(clientY: number) {
  lastClientY = clientY
  dragOver.value = indexAtY(clientY)
  if (!isSoft()) actualizarVisualArrastre(clientY)
}

const wsPorId = computed(() => new Map((board.value?.workspaces ?? []).map((w) => [w.id, w])))

function indexAtY(clientY: number): number {
  if (!cardMids.length) return 0
  const y = clientY + (scroller.value?.scrollTop ?? 0)
  for (let i = 0; i < cardMids.length; i++) {
    if (y < cardMids[i]!) return i
  }
  return cardMids.length - 1
}

function commitOrder(ids: string[]) {
  void guardarOrden(ids)
}

function esActivoId(id: string): boolean {
  const w = wsPorId.value.get(id)
  return w ? wsEsActivoParaOrden(w) : false
}

function moveCard(from: number, to: number) {
  if (from === to) return
  const visual = moverEnOrden(manualIds.value, from, to)
  commitOrder(ordenTrasArrastreQuietos(visual, esActivoId, ordenGuardado.value))
}

function togglePlegada(wsId: string) {
  const cur = plegadasGuardado.value
  const on = cur.includes(wsId)
  const next = on ? cur.filter((id) => id !== wsId) : [...cur, wsId]
  void guardarPlegadas(next)
}

function scrollTarjetaAVista(wsId: string) {
  void nextTick().then(() => {
    requestAnimationFrame(() => {
      const el = list.value?.$el.querySelector<HTMLElement>(`[data-ws="${wsId}"]`)
      if (!el) return
      el.scrollIntoView({ block: 'nearest', behavior: isSoft() ? 'auto' : 'smooth' })
    })
  })
}

function onReorderKey(index: number, delta: -1 | 1) {
  onReorderMove(index, delta)
}

function onReorderMove(index: number, delta: -1 | 1) {
  const wsId = workspaces.value[index]?.id
  const to = destinoReordenQuieto(index, delta, workspaces.value)
  if (to === null || !wsId) return
  moveCard(index, to)
  scrollTarjetaAVista(wsId)
}

function onGripCancelHold() {
  if (gripArmed.value) return
  clearTimeout(gripHold)
}

function onGripDown(index: number, e: PointerEvent) {
  if (e.button !== 0) return
  const ws = workspaces.value[index]
  if (!ws || wsEsActivoParaOrden(ws)) return
  const el = e.currentTarget as HTMLElement
  if (e.pointerType === 'touch') e.preventDefault()
  const arm = () => {
    gripArmed.value = true
    haptic(8)
    e.preventDefault()
    gripStart = { index, id: e.pointerId, el }
    dragFrom.value = index
    dragOver.value = index
    document.documentElement.classList.add(ROOT_DRAG)
    liftEl = el.closest('.ws') as HTMLElement | null
    liftStartY = e.clientY
    lastClientY = e.clientY
    lastShiftTo = -1
    medirTarjetas()
    scrollAcc = 0
    if (liftEl && !isSoft()) {
      liftStep = liftEl.getBoundingClientRect().height + 2
      liftEl.classList.add('drag-float')
      actualizarVisualArrastre(e.clientY)
    }
    scrollRaf = requestAnimationFrame(autoScrollArrastre)
    try {
      el.setPointerCapture(e.pointerId)
    } catch {
      /* captura perdida: el arrastre sigue con listeners en window */
    }
    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== gripStart?.id) return
      if (ev.cancelable) ev.preventDefault()
      seguirArrastre(ev.clientY)
    }
    const end = (ev: PointerEvent) => {
      if (ev.pointerId !== gripStart?.id) return
      const from = dragFrom.value
      const to = dragOver.value
      if (el.hasPointerCapture(ev.pointerId)) el.releasePointerCapture(ev.pointerId)
      const commit = () => {
        detachDrag()
        if (from !== null && to !== null && from !== to) moveCard(from, to)
      }
      if (isSoft() || !liftEl) {
        commit()
        return
      }
      if (scrollRaf) cancelAnimationFrame(scrollRaf)
      scrollRaf = 0
      const step = liftStep
      const moved = from !== null && to !== null && from !== to
      const targetY = moved ? (to! - from!) * step : 0
      const card = liftEl
      run(() => {
        gsap.to(card, {
          y: targetY,
          scale: 1,
          duration: 0.22,
          ease: 'power2.out',
          onComplete: commit,
        })
      })
    }
    const cancel = (ev: PointerEvent) => {
      if (ev.pointerId !== gripStart?.id) return
      if (!gripArmed.value) return
      end(ev)
    }
    const opts = { capture: true }
    window.addEventListener('pointermove', move, opts)
    window.addEventListener('pointerup', end, opts)
    window.addEventListener('pointercancel', cancel, opts)
    dragListeners = () => {
      window.removeEventListener('pointermove', move, opts)
      window.removeEventListener('pointerup', end, opts)
      window.removeEventListener('pointercancel', cancel, opts)
    }
  }
  gripArmed.value = false
  if (e.pointerType === 'touch') {
    clearTimeout(gripHold)
    gripHold = setTimeout(arm, GRIP_MS)
    return
  }
  arm()
}

onBeforeUnmount(() => {
  clearTimeout(gripHold)
  detachDrag()
})

function calcReorderUi(index: number): ReorderUi | null {
  const ws = workspaces.value[index]
  if (!ws || wsEsActivoParaOrden(ws)) return null
  const list = workspaces.value
  return {
    index,
    total: list.length,
    canUp: destinoReordenQuieto(index, -1, list) !== null,
    canDown: destinoReordenQuieto(index, 1, list) !== null,
    dropBefore: dragOver.value === index && dragFrom.value !== null && dragFrom.value !== index,
    lifting: dragFrom.value === index,
    arming: gripArmed.value && dragFrom.value === index,
  }
}
let reorderPrev: (ReorderUi | null)[] = []
const reorderList = computed(() => {
  reorderPrev = compartir(reorderPrev, workspaces.value.map((_, i) => calcReorderUi(i)))
  return reorderPrev
})
const scroller = ref<HTMLElement | null>(null)
const tabs = computed(() => workspaces.value.reduce((n, w) => n + w.tabs.length, 0))
const updated = computed(() => ago(board.value?.updated_at, now.value))
watch(highlight, async (h) => {
  if (!h) return
  await nextTick()
  requestAnimationFrame(() => {
    const el = [...(scroller.value?.querySelectorAll<HTMLElement>('[data-pane]') ?? [])].find((e) => e.dataset.pane === h.paneId)
    el?.scrollIntoView({ block: 'center', behavior: isSoft() ? 'auto' : 'smooth' })
  })
})
const { run } = useGsap()
const list = ref<{ $el: HTMLElement } | null>(null)
const cards = () => [...(list.value?.$el.children ?? [])] as HTMLElement[]
let entered = false

onMounted(() => {
  iniciarMudanza()
  const els = cards()
  if (!els.length) return
  entered = true
  if (isSoft()) {
    run(() => gsap.from(els, { opacity: 0, duration: 0.3, clearProps: 'opacity' }))
    return
  }
  run(() =>
    gsap.from(els, {
      y: 26,
      opacity: 0,
      scale: 0.985,
      duration: 0.35,
      ease: 'power3.out',
      stagger: { each: 0.055, amount: Math.min(0.6, els.length * 0.055) },
      delay: 0.12,
      clearProps: 'transform,opacity',
    }),
  )
})

let flipState: Flip.FlipState | null = null
let activeFlip: gsap.core.Timeline | null = null
watch(
  () => workspaces.value.map((w) => w.id).join(),
  (ids, old) => {
    if (!old || ids === old || !entered) return
    const prev = old.split(',')
    const kept = new Set(ids.split(',').filter((id) => prev.includes(id)))
    const moved = cards().filter((c) => kept.has(c.dataset.ws ?? ''))
    // Un reorden encima de otro dejaba alto/ancho inline viejos: la tarjeta quedaba cortada.
    activeFlip?.progress(1).kill()
    activeFlip = null
    flipState = moved.length ? Flip.getState(moved) : null
    nextTick(() => {
      const st = flipState
      flipState = null
      if (!st) return
      if (isSoft()) return
      const next = ids.split(',')
      const rose = next.findIndex((id, i) => prev.indexOf(id) > i)
      const riser = rose >= 0 ? cards().find((c) => c.dataset.ws === next[rose]) : null
      const shifted = cards().filter((c) => {
        const id = c.dataset.ws ?? ''
        return c !== riser && prev.includes(id) && prev.indexOf(id) !== next.indexOf(id)
      })
      run(() => {
        riser?.classList.add('flying')
        const done = () => {
          riser?.classList.remove('flying')
          gsap.set(st.targets, { clearProps: 'width,height,transform,zIndex' })
          activeFlip = null
        }
        activeFlip = Flip.from(st, {
          duration: 0.75,
          ease: 'power3.inOut',
          stagger: 0.015,
          zIndex: 1,
          onComplete: done,
          onInterrupt: done,
        })
        if (shifted.length) gsap.fromTo(shifted, { opacity: 0.3 }, { opacity: 1, duration: 0.8, ease: 'power2.in', clearProps: 'opacity' })
        if (riser) {
          gsap.fromTo(riser, { '--lift': 1 }, { '--lift': 0, duration: 1.6, ease: 'power2.out', delay: 0.2 })
        }
      })
    })
  },
  { flush: 'pre' },
)

function onEnter(el: Element, done: () => void) {
  if (!entered) return done()
  const e = el as HTMLElement
  if (isSoft()) {
    run(() => gsap.from(e, { opacity: 0, duration: 0.25, onComplete: done }))
    return
  }
  run(() =>
    gsap.from(e, {
      opacity: 0,
      y: -14,
      scale: 0.96,
      duration: 0.7,
      ease: 'back.out(1.6)',
      clearProps: 'transform,opacity',
      onComplete: done,
    }),
  )
}
function onLeave(el: Element, done: () => void) {
  const e = el as HTMLElement
  const r = e.getBoundingClientRect()
  const pr = e.parentElement!.getBoundingClientRect()
  gsap.set(e, { position: 'absolute', top: r.top - pr.top, left: r.left - pr.left, width: r.width })
  run(() => gsap.to(e, { opacity: 0, scale: 0.95, x: isSoft() ? 0 : 24, duration: isSoft() ? 0.2 : 0.35, ease: 'power2.in', onComplete: done }))
}

const reconnecting = computed(() => boardState.value.connection === 'reconnecting')
const terminalesSinConexion = computed(() => board.value?.terminales === 'sin_conexion')
const conflictosIds = computed(() => board.value?.conflictos ?? [])
const conflictosTexto = computed(() => conflictosIds.value.join(', '))
const guardianCaido = computed(() => !terminalesSinConexion.value && (board.value?.caidos ?? []).includes('guardian'))
const tableroMeta = computed(() => {
  const n = workspaces.value.length
  const w = `${n} ${n === 1 ? 'workspace' : 'workspaces'}`
  const t = `${tabs.value} ${tabs.value === 1 ? 'tab' : 'tabs'}`
  return updated.value ? `${w} · ${t} · ${updated.value}` : `${w} · ${t}`
})
</script>

<template>
  <ViewFrame title="Tablero" :subtitle="tableroMeta" aria-label="Tablero">
    <div class="nt-row">
      <button type="button" class="nt-chip" aria-label="Nueva terminal" @click="abrirNueva">
        <Icon name="plus" :size="14" />
        <span class="nt-chip-txt">Nueva terminal</span>
      </button>
      <button
        type="button"
        class="nt-chip nt-clock"
        aria-label="Retomar una sesión vieja"
        title="Retomar una sesión vieja"
        @click="abrirRetomar"
      >
        <Icon name="clock" :size="14" />
      </button>
    </div>
    <LimpiezaChip />
    <MudanzaChip />

    <Transition name="banner">
      <div v-if="reconnecting" class="banner" role="status">
        <span class="banner-dot" />
        Perdí la conexión con las terminales. Reintentando…
      </div>
    </Transition>
    <Transition name="banner">
      <div v-if="terminalesSinConexion" class="banner" role="status">
        Sin conexión con las terminales
      </div>
    </Transition>
    <Transition name="banner">
      <div v-if="guardianCaido" class="banner" role="status">
        Sin conexión con las terminales propias. Reintentando…
      </div>
    </Transition>
    <Transition name="banner">
      <div v-if="conflictosIds.length" class="banner" role="status">
        Conflicto de ids: {{ conflictosTexto }}
      </div>
    </Transition>

    <div ref="scroller" class="scroll view-scroll">
      <TransitionGroup ref="list" v-spotlight="'.ws'" tag="div" class="list" :css="false" @enter="onEnter" @leave="onLeave">
        <WorkspaceCard
          v-for="(ws, i) in workspaces"
          :key="ws.id"
          :data-ws="ws.id"
          :ws="ws"
          :now="now"
          :reorder="reorderList[i]"
          :plegada="plegadasGuardado.includes(ws.id)"
          :plegadas-err="plegadasError && plegadasGuardado.includes(ws.id) ? plegadasError : ''"
          @reorder-key="onReorderKey(i, $event)"
          @reorder-move="onReorderMove(i, $event)"
          @grip-down="onGripDown(i, $event)"
          @grip-cancel-hold="onGripCancelHold"
          @toggle-plegada="togglePlegada(ws.id)"
          @sumar-pestana="sumarPestana(ws.id)"
        />
      </TransitionGroup>
      <EmptyState v-if="board && !workspaces.length" title="No hay sesiones abiertas">Cuando abras un workspace aparece acá.</EmptyState>
      <p v-if="hayOrdenManual || ordenError" class="orden-reset">
        <span v-if="ordenError" class="orden-err" role="alert">{{ ordenError }}</span>
        <button type="button" class="orden-reset-btn" @click="volverOrdenAutomatico">Volver al orden automático</button>
      </p>
    </div>
    <MudanzaSheet />
    <NuevaTerminalSheet :open="nuevaAbierta" :grupo-inicial="nuevaGrupo" @close="nuevaAbierta = false" />
    <RetomarSesionSheet :open="retomarAbierta" @close="retomarAbierta = false" />
  </ViewFrame>
</template>

<style scoped>
.nt-row {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  max-width: 100%;
}
.nt-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  min-width: 0;
  margin: 0;
  padding: 0 14px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}
.nt-row > .nt-chip:not(.nt-clock) {
  flex: 1 1 auto;
  max-width: 100%;
}
.nt-chip-txt {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nt-chip:hover {
  color: var(--text);
  border-color: color-mix(in srgb, var(--accent) 50%, transparent);
}
.nt-clock {
  flex: none;
  width: 32px;
  height: 32px;
  min-height: 32px;
  padding: 0;
  justify-content: center;
  border-radius: 50%;
}
.nt-chip:not(.nt-clock) :deep(svg) {
  color: var(--accent);
}
.nt-clock :deep(svg) {
  color: var(--text-2);
}
.nt-clock:hover :deep(svg) {
  color: var(--text);
}
.scroll {
  flex: 1;
  min-height: 0;
  overflow-x: hidden;
  margin: 0 calc(-1 * var(--gutter));
  padding: 0 var(--gutter-end) 8px var(--gutter);
}
.list {
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 2px;
}
:global(html.orq-arrastrando-tablero) {
  touch-action: none;
}
:root.orq-arrastrando-tablero .scroll {
  touch-action: none;
}
.orden-reset {
  margin: 10px 0 4px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 6px;
}
.orden-err {
  font-size: 13px;
  color: var(--danger);
}
.orden-reset-btn {
  border: none;
  background: none;
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text-3);
  cursor: pointer;
  border-radius: var(--r-pill);
  transition: color 0.2s, background 0.2s;
}
.orden-reset-btn:hover,
.orden-reset-btn:focus-visible {
  color: var(--text-2);
  background: var(--surface-hover);
}


.banner {
  margin: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 12px;
  font-size: var(--t-md);
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  border-radius: var(--r-md);
}
.banner-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  animation: blink 1s steps(2, jump-none) infinite;
  box-shadow: 0 0 8px currentColor;
}
@keyframes blink {
  50% { opacity: 0.2; }
}
.banner-enter-active,
.banner-leave-active {
  transition: opacity 0.3s, transform 0.4s var(--ease-out);
}
.banner-enter-from,
.banner-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}
:root[data-motion='soft'] .banner-dot {
  animation: none;
}

</style>
