<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, ref, watch } from 'vue'
import { auth, boardState, boot, viewRequest } from './state/app'
import { summarize } from './state/boardReducer'
import LoginScreen from './components/LoginScreen.vue'
import TopBar from './components/TopBar.vue'
import CartelRapido from './components/CartelRapido.vue'
import BoardPanel from './components/BoardPanel.vue'
import MobileTabs from './components/MobileTabs.vue'
import { initTerminalNav, openTerminalId } from './state/terminales'
import { correrGancho, piezas } from './piezas'
import { initMrsNav, mrs, mrsRequest, mrsVisible, pendientesMrs } from './state/mrs'
import { mobilePageIndex, mobilePageOrder, type MobileView } from './lib/mobileSections'
import { initLibraryNav, lib, libRequest, libVisible } from './state/biblioteca'
import { notasVisible, pendientes as notasPendientes } from './state/notas'
import { cierreSinTransicion, closeSessionChat, coldLink, initSessionNav, openSessionId, terminarCierreSinTransicion } from './state/session'
import LogoLoader from './components/LogoLoader.vue'
import { desktop } from './lib/viewport'
import Icon from './components/Icon.vue'
import { cargarSessionChatView } from './lib/precarga'
const SessionChatView = defineAsyncComponent(cargarSessionChatView)
const TerminalViewer = defineAsyncComponent(() => import('./components/TerminalViewer.vue'))
const BibliotecaView = defineAsyncComponent(() => import('./components/BibliotecaView.vue'))
const NotasView = defineAsyncComponent(() => import('./components/NotasView.vue'))
const BibOverlay = defineAsyncComponent(() => import('./components/BibOverlay.vue'))
const TerminalVivo = defineAsyncComponent(() => import('./components/TerminalVivo.vue'))
const MrsView = defineAsyncComponent(() => import('./components/MrsView.vue'))
const CloseSheet = defineAsyncComponent(() => import('./components/CloseSheet.vue'))
const LimpiezaSheet = defineAsyncComponent(() => import('./components/LimpiezaSheet.vue'))
const TerminalConfirmSheet = defineAsyncComponent(() => import('./components/TerminalConfirmSheet.vue'))
const AjustesView = defineAsyncComponent(() => import('./components/AjustesView.vue'))
const EntornosView = defineAsyncComponent(() => import('./components/EntornosView.vue'))
const KitView = defineAsyncComponent(() => import('./components/KitView.vue'))
const TareasView = defineAsyncComponent(() => import('./components/TareasView.vue'))
const CommandPalette = defineAsyncComponent(() => import('./components/CommandPalette.vue'))
import { ajustesOpen } from './state/ajustes'
import { abrirDesdeRuta, entornosOpen } from './state/entornos'
import { kitOpen, resetKit } from './state/kit'
import { resetTareas, tareasOpen } from './state/tareas'
import { initLimpieza } from './state/limpieza'
import { initAvisos } from './state/avisos'
import { initPedidosPestana } from './state/pedidosPestana'
import { initOrdenTablero } from './state/ordenTablero'
import { initAtajos } from './state/atajos'
import AmbientBackdrop from './components/AmbientBackdrop.vue'
import DemoAviso from './components/DemoAviso.vue'
import { DEMO } from './lib/demoActual'
import { gsap, haptic, isSoft, unlocked, useGsap } from './motion'
import { useKeyboard } from './lib/keyboard'
import Divisor from './components/Divisor.vue'
import { useAncho } from './lib/divisor'

const { run } = useGsap()

type View = MobileView
const view = ref<View>('board')
const montadas = piezas()
const seccionesPieza = montadas.flatMap((p) => (p.seccion ? [{ id: p.id, ...p.seccion }] : []))
const esVistaPieza = (v: View) => seccionesPieza.some((s) => s.id === v)
const PAGES = computed(() => mobilePageOrder(mrs.habilitado, seccionesPieza))
const pageOf = (v: View) => mobilePageIndex(PAGES.value, v)
const mobileCols = computed(() => (!desktop.value ? PAGES.value.length : 6))
watch(
  () => mrs.habilitado,
  (on) => {
    if (!on && view.value === 'mrs') view.value = 'board'
    if (!desktop.value) nextTick(() => render(pageOf(view.value)))
  },
)
const keyboard = useKeyboard()
const kbOpen = computed(() => !desktop.value && keyboard.open.value)
const attention = computed(() => {
  const s = summarize(boardState.value.board)
  return s.needs
})

watch(viewRequest, (r) => {
  if (!r) return
  view.value = 'board'
})

// The section lives in `view`; TopBar and deep links drive it through `libVisible` / `libRequest`.
watch(view, (v) => (libVisible.value = v === 'biblioteca'), { immediate: true })
watch(libVisible, (on) => {
  if (on && view.value !== 'biblioteca') view.value = 'biblioteca'
  else if (!on && view.value === 'biblioteca') view.value = 'board'
})
watch(libRequest, (r) => r && (view.value = 'biblioteca'))
watch(view, (v) => (notasVisible.value = v === 'notas'), { immediate: true })
watch(notasVisible, (on) => {
  if (on && view.value !== 'notas') view.value = 'notas'
  else if (!on && view.value === 'notas') view.value = 'board'
})
watch(auth, (a) => a !== 'ready' && (resetKit(), resetTareas()))
for (const s of seccionesPieza) {
  watch(view, (v) => (s.visible.value = v === s.id), { immediate: true })
  watch(s.visible, (on) => {
    if (on && view.value !== s.id) view.value = s.id
    else if (!on && view.value === s.id) view.value = 'board'
  })
  if (s.pedido) watch(s.pedido, (r) => r && (view.value = s.id))
}
const overlaysPieza = montadas.filter((p) => p.overlay)
const apagarPiezas = () => seccionesPieza.forEach((s) => (s.visible.value = false))
watch(view, (v) => (mrsVisible.value = v === 'mrs'), { immediate: true })
watch(mrsVisible, (on) => {
  if (on && view.value !== 'mrs') view.value = 'mrs'
  else if (!on && view.value === 'mrs') view.value = 'board'
})
watch(mrsRequest, (r) => {
  if (!r) return
  if (openSessionId.value) closeSessionChat()
  if (openTerminalId.value) openTerminalId.value = null
  view.value = 'mrs'
})
watch(openSessionId, (id, prev) => {
  if (id && desktop.value) {
    libVisible.value = mrsVisible.value = notasVisible.value = false
    apagarPiezas()
  }
  if (id && openTerminalId.value) openTerminalId.value = null
})
watch(openTerminalId, (id) => {
  if (id && desktop.value) {
    libVisible.value = mrsVisible.value = notasVisible.value = false
    apagarPiezas()
  }
  if (id && openSessionId.value) closeSessionChat()
})

// ---------- desktop: ancho del tablero, arrastrable ----------
const tablero = useAncho({ clave: 'orq.anchoTablero', min: 320, minResto: 560, porDefecto: (c) => c * 0.4 })
const columnas = computed(() => desktop.value && view.value !== 'biblioteca' && !esVistaPieza(view.value) && view.value !== 'mrs' && view.value !== 'notas')

// ---------- desktop: the right column swaps between conversations ----------
const layer = ref<HTMLElement | null>(null)
watch([openSessionId, openTerminalId], async ([sid, tid], [psid, ptid]) => {
  const id = sid || tid
  const prev = psid || ptid

  if (!desktop.value) return
  await nextTick()
  const soft = isSoft()
  const el = id && prev ? layer.value : null
  if (!el) return
  run(() =>
    gsap.fromTo(el, soft ? { opacity: 0 } : { opacity: 0, x: id ? 18 : -18 }, { opacity: 1, x: 0, duration: soft ? 0.18 : 0.38, ease: 'power3.out', clearProps: 'transform,opacity' }),
  )
})

// ---------- mobile pager: board | MRs | piezas | notes | library on one track, finger-tracked ----------
const panes = ref<HTMLElement | null>(null)
const track = ref<HTMLElement | null>(null)
const boardPane = ref<{ $el: HTMLElement } | null>(null)
const bibPane = ref<{ $el: HTMLElement } | null>(null)
const piezaPanes: Record<string, { $el: HTMLElement } | null> = {}
const mrsPane = ref<{ $el: HTMLElement } | null>(null)
const notasPane = ref<{ $el: HTMLElement } | null>(null)
const tabsBar = ref<{ setProgress: (p: number) => void } | null>(null)
const pager = { p: 0 }
let pagerTween: gsap.core.Tween | null = null

const fade = (p: number, at: number) => 1 - 0.55 * Math.min(1, Math.abs(p - at))


function render(p: number) {
  pager.p = p
  if (desktop.value) return
  if (!track.value) return
  gsap.set(track.value, { xPercent: -100 * p })
  const at = (v: View) => pageOf(v)
  if (boardPane.value) gsap.set(boardPane.value.$el, { opacity: fade(p, at('board')) })
  if (mrsPane.value) gsap.set(mrsPane.value.$el, { opacity: fade(p, at('mrs')) })
  for (const s of seccionesPieza) {
    const el = piezaPanes[s.id]?.$el
    if (el) gsap.set(el, { opacity: fade(p, at(s.id)) })
  }
  if (notasPane.value) gsap.set(notasPane.value.$el, { opacity: fade(p, at('notas')) })
  if (bibPane.value) gsap.set(bibPane.value.$el, { opacity: fade(p, at('biblioteca')) })
  tabsBar.value?.setProgress(Math.min(PAGES.value.length - 1, Math.max(0, p)))
}

function settle(target: number, velocity = 0) {
  if (desktop.value) return
  pagerTween?.kill()
  if (isSoft()) {
    render(target)
    if (track.value) run(() => gsap.fromTo(track.value, { opacity: 0.6 }, { opacity: 1, duration: 0.18 }))
    return
  }
  const dist = Math.abs(target - pager.p)
  pagerTween = run(() =>
    gsap.to(pager, {
      p: target,
      duration: Math.max(0.32, Math.min(0.7, 0.62 * dist - Math.abs(velocity) * 0.08 + 0.12)),
      ease: 'expo.out',
      onUpdate: () => render(pager.p),
    }),
  )
}

function resetPager() {
  pagerTween?.kill()
  const els = [track.value, boardPane.value?.$el, mrsPane.value?.$el, ...seccionesPieza.map((s) => piezaPanes[s.id]?.$el), notasPane.value?.$el, bibPane.value?.$el].filter(Boolean)
  if (els.length) {
    gsap.killTweensOf(els)
    gsap.set(els, { clearProps: 'transform,opacity' })
  }
}

watch(view, (v) => {
  if (!desktop.value && !dragging) settle(pageOf(v))
})
// The shell mounts after the splash leaves, so the starting page is placed once the track exists.
watch(track, (el) => el && !desktop.value && render(pageOf(view.value)), { flush: 'post' })
watch(desktop, async (d) => {
  await nextTick()
  if (d) resetPager()
  else render(pageOf(view.value))
})

const NOSWIPE = '.sess-layer, .md-table, .md-code, textarea, input, select, .brief-doc, .m-viewer, .sheet-bg, [data-noswipe]'
let dragging = false
let g: { id: number; x0: number; y0: number; p0: number; w: number; lock: 'x' | 'y' | null; lx: number; lt: number; v: number } | null = null

function onDown(e: PointerEvent) {
  if (desktop.value || e.pointerType === 'mouse' || !panes.value) return
  if ((e.target as Element).closest(NOSWIPE)) return
  g = { id: e.pointerId, x0: e.clientX, y0: e.clientY, p0: pager.p, w: panes.value.clientWidth, lock: null, lx: e.clientX, lt: e.timeStamp, v: 0 }
}
function onMove(e: PointerEvent) {
  if (!g || e.pointerId !== g.id) return
  const dx = e.clientX - g.x0
  const dy = e.clientY - g.y0
  if (!g.lock) {
    if (Math.abs(dx) < 9 && Math.abs(dy) < 9) return
    g.lock = Math.abs(dx) > Math.abs(dy) * 1.25 ? 'x' : 'y'
    if (g.lock === 'y') {
      g = null
      return
    }
    dragging = true
    pagerTween?.kill()
    panes.value?.setPointerCapture(e.pointerId)
  }
  const dt = Math.max(1, e.timeStamp - g.lt)
  g.v = 0.7 * g.v + 0.3 * ((e.clientX - g.lx) / dt)
  g.lx = e.clientX
  g.lt = e.timeStamp
  let p = g.p0 - dx / g.w
  if (p < 0) p = -Math.min(0.12, (-p) * 0.3)
  const last = PAGES.value.length - 1
  if (p > last) p = last + Math.min(0.12, (p - last) * 0.3)
  render(p)
}
function onUp(e: PointerEvent) {
  if (!g || e.pointerId !== g.id) return
  const st = g
  g = null
  if (st.lock !== 'x') return
  const flick = Math.abs(st.v) > 0.35
  const raw = flick ? (st.v < 0 ? Math.ceil(pager.p - 0.05) : Math.floor(pager.p + 0.05)) : Math.round(pager.p)
  const target = Math.min(PAGES.value.length - 1, Math.max(0, raw))
  const next = PAGES.value[target]
  if (next !== view.value) haptic(8)
  view.value = next
  dragging = false
  settle(target, st.v)
}

// ---------- power-on after unlock ----------
const sweep = ref<HTMLElement | null>(null)
watch(auth, async (a, prev) => {
  if (a !== 'ready' || prev === 'ready') return
  await nextTick()
  coldLink.value = false
  initLimpieza()
  abrirDesdeRuta()
  for (const p of montadas) void correrGancho(p, 'alEntrar')
  if (!desktop.value) render(pageOf(view.value))
  if (!unlocked.value || isSoft() || !sweep.value) return
  unlocked.value = false
  run(() =>
    gsap
      .timeline()
      .fromTo(sweep.value, { yPercent: -100, opacity: 1 }, { yPercent: 0, y: window.innerHeight, duration: 0.9, ease: 'power2.inOut' })
      .to(sweep.value, { opacity: 0, duration: 0.25 }, '-=0.25'),
  )
})
onMounted(() => {
  initSessionNav()
  initTerminalNav()
  initLibraryNav()
  for (const p of montadas) void correrGancho(p, 'init')
  initMrsNav()
  initAvisos()
  initPedidosPestana()
  initOrdenTablero()
  initAtajos()
  if (auth.value === 'ready' && !desktop.value) render(pageOf(view.value))
})
</script>

<template>
  <AmbientBackdrop />
  <DemoAviso v-if="DEMO" />
  <Transition :name="coldLink ? 'screen-cold' : 'screen'" mode="out-in">
    <div v-if="auth === 'checking'" key="checking" class="splash">
      <LogoLoader />
    </div>

    <LoginScreen
      v-else-if="auth === 'login'"
      key="login"
      :class="{ 'kb-open': kbOpen }"
      :style="kbOpen && keyboard.height.value ? { '--app-h': `${keyboard.height.value}px`, '--vv-top': `${keyboard.top.value}px` } : undefined"
    />

    <div v-else-if="auth === 'forbidden' || auth === 'offline'" key="error" class="fallback">
      <p class="fallback-code mono">{{ auth === 'forbidden' ? '403' : 'sin señal' }}</p>
      <h1>{{ auth === 'forbidden' ? 'Esta red no tiene acceso' : 'No llego al servidor' }}</h1>
      <p class="fallback-sub">
        {{
          auth === 'forbidden'
            ? 'Colmena solo atiende desde la LAN o Tailscale.'
            : 'Fijate que Colmena esté corriendo en la notebook.'
        }}
      </p>
      <button class="fallback-btn" @click="boot()"><Icon name="refresh" :size="15" /> Reintentar</button>
    </div>

    <div
      v-else
      key="app"
      class="shell"
      :class="{ desktop, [`view-${view}`]: !desktop, 'kb-open': kbOpen }"
      :style="kbOpen && keyboard.height.value ? { '--app-h': `${keyboard.height.value}px` } : undefined"
    >
      <i ref="sweep" class="sweep" aria-hidden="true" />
      <TopBar :compact="!desktop" />
      <main
        ref="panes"
        class="panes"
        :style="desktop ? { '--tablero': `${tablero.ancho.value}px` } : undefined"
        @pointerdown="onDown"
        @pointermove="onMove"
        @pointerup="onUp"
        @pointercancel="onUp"
      >
        <Divisor v-if="desktop" v-show="columnas" :ancho="tablero" label="Ancho del tablero" />
        <div
          ref="track"
          class="track"
          :style="!desktop ? { gridTemplateColumns: `repeat(${mobileCols}, 100%)` } : undefined"
        >
          <BoardPanel ref="boardPane" class="pane pane-board" :inert="!desktop && view !== 'board'" />
          <MrsView
            v-if="mrs.habilitado"
            ref="mrsPane"
            class="pane pane-mrs"
            :class="{ off: desktop && view !== 'mrs' }"
            :visible="view === 'mrs'"
            :inert="view !== 'mrs'"
          />
          <component
            :is="sp.vista"
            v-for="sp in seccionesPieza"
            :key="sp.id"
            :ref="(el: unknown) => (piezaPanes[sp.id] = el as { $el: HTMLElement } | null)"
            class="pane pane-pieza"
            :class="{ off: desktop && view !== sp.id }"
            :visible="view === sp.id"
            :inert="view !== sp.id"
          />
          <NotasView ref="notasPane" class="pane pane-notas" :class="{ off: desktop && view !== 'notas' }" :visible="view === 'notas'" :inert="view !== 'notas'" />
          <BibliotecaView ref="bibPane" class="pane pane-bib" :class="{ off: desktop && view !== 'biblioteca' }" :visible="view === 'biblioteca'" :inert="view !== 'biblioteca'" />
        </div>
        <Transition :name="cierreSinTransicion ? 'sess-nativa' : coldLink ? 'sess-cold' : 'sess'" @after-leave="terminarCierreSinTransicion">
          <div v-if="openSessionId" ref="layer" class="sess-layer">
            <SessionChatView :desktop="desktop" />
          </div>
          <div v-else-if="openTerminalId" ref="layer" class="sess-layer">
            <TerminalViewer :desktop="desktop" />
          </div>
        </Transition>
      </main>
      <MobileTabs v-if="!desktop && !kbOpen && !openSessionId && !openTerminalId" ref="tabsBar" v-model="view" :attention="attention" :fresh="lib.newCount" :mrs-pending="pendientesMrs" :notas-pending="notasPendientes" />
    </div>
  </Transition>

  <CloseSheet />
  <LimpiezaSheet />
  <TerminalConfirmSheet />
  <Transition name="aj">
    <AjustesView v-if="auth === 'ready' && ajustesOpen" />
  </Transition>
  <Transition name="aj">
    <EntornosView v-if="auth === 'ready' && entornosOpen" />
  </Transition>
  <Transition name="aj">
    <KitView v-if="auth === 'ready' && kitOpen" />
  </Transition>
  <Transition name="aj">
    <TareasView v-if="auth === 'ready' && tareasOpen" />
  </Transition>
  <BibOverlay v-if="auth === 'ready'" />
  <TerminalVivo v-if="auth === 'ready'" />
  <template v-if="auth === 'ready'">
    <component :is="p.overlay" v-for="p in overlaysPieza" :key="p.id" />
  </template>
  <CommandPalette v-if="auth === 'ready'" />
  <CartelRapido v-if="auth === 'ready'" />

</template>

<style scoped>
.shell {
  position: relative;
  z-index: 1;
  height: var(--app-h, 100dvh);
  display: grid;
  grid-template-rows: auto 1fr;
  background: radial-gradient(1200px 500px at 0% -10%, var(--accent-soft), transparent 60%);
}
.sweep {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 38vh;
  z-index: 40;
  pointer-events: none;
  opacity: 0;
  background: linear-gradient(180deg, transparent, color-mix(in srgb, var(--accent) 7%, transparent) 70%, color-mix(in srgb, var(--accent) 22%, transparent) 98%, var(--accent));
  border-bottom: 1px solid var(--accent);
  box-shadow: 0 6px 30px -4px var(--accent);
}
.shell:not(.desktop) {
  grid-template-rows: auto 1fr auto;
}
.panes {
  position: relative;
  min-height: 0;
  overflow: hidden;
  touch-action: pan-y;
}
.track {
  height: 100%;
  display: grid;
  grid-template-columns: repeat(6, 100%);
  will-change: transform;
}
.shell:not(.desktop) .track :deep(*) {
  touch-action: pan-y;
}
.shell:not(.desktop) .track :deep(:is(.md-table, .md-code, .brief-doc, textarea, input, [data-noswipe])),
.shell:not(.desktop) .track :deep(:is(.md-table, .md-code, .brief-doc, [data-noswipe]) *) {
  touch-action: auto;
}
.desktop .track {
  grid-template-columns: var(--tablero, 40%) minmax(0, 1fr);
  will-change: auto;
}
.desktop .pane-bib,
.desktop .pane-mrs,
.desktop .pane-notas,
.desktop .pane-pieza {
  position: absolute;
  inset: 0;
  z-index: 7;
}
.desktop .pane-bib.off,
.desktop .pane-mrs.off,
.desktop .pane-notas.off,
.desktop .pane-pieza.off {
  display: none;
}
.sess-layer {
  position: absolute;
  inset: 0;
  z-index: 6;
  background: var(--bg);
}
.desktop .sess-layer {
  left: var(--tablero, 40%);
  border-left: 1px solid var(--line);
}
.sess-enter-active { transition: transform 0.55s var(--spring), opacity 0.3s; }
.sess-leave-active { transition: opacity 0.2s; }
.sess-enter-from { transform: translateX(100%); }
.desktop .sess-enter-from { transform: translateX(24px); opacity: 0; }
.sess-leave-to { opacity: 0; }
:root[data-motion='soft'] .sess-enter-active { transition: opacity 0.2s; }
:root[data-motion='soft'] .sess-enter-from { transform: none; opacity: 0; }
.pane {
  min-height: 0;
  min-width: 0;
}
.desktop .pane-board {
  border-right: 1px solid var(--line);
}

.splash {
  height: 100dvh;
  display: grid;
  place-items: center;
}
.fallback {
  height: 100dvh;
  display: grid;
  place-content: center;
  justify-items: start;
  padding: 24px;
  max-width: 520px;
  margin: 0 auto;
}
.fallback-code {
  color: var(--st-blocked);
  font-size: 13px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin: 0 0 10px;
}
.fallback h1 {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: clamp(26px, 6vw, 38px);
  letter-spacing: -0.025em;
  line-height: 1.05;
  margin: 0 0 10px;
}
.fallback-sub {
  color: var(--text-2);
  margin: 0 0 22px;
}
.fallback-btn {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  transition: background 0.2s, border-color 0.2s;
}
.fallback-btn:hover {
  background: var(--surface-hover);
  border-color: var(--accent-line);
}

.screen-enter-active { transition: opacity 0.45s var(--ease-out), transform 0.55s var(--ease-out); }
.screen-leave-active { transition: opacity 0.2s var(--ease-out), transform 0.25s var(--ease-out); }
.screen-enter-from { opacity: 0; transform: translateY(8px); }
:root[data-motion='soft'] .screen-enter-from { transform: none; }
.screen-leave-to { opacity: 0; transform: scale(0.985); }
.screen-cold-leave-active { transition: opacity 0.12s; }
.screen-cold-leave-to { opacity: 0; }

.aj-enter-active { transition: transform 0.55s var(--spring), opacity 0.3s; }
.aj-leave-active { transition: transform 0.3s var(--ease-out), opacity 0.25s; }
.aj-enter-from { transform: translateX(100%); }
.aj-leave-to { opacity: 0; transform: translateX(40%); }
@media (min-width: 1024px) {
  .aj-enter-from { transform: scale(0.985) translateY(10px); opacity: 0; }
  .aj-leave-to { transform: scale(0.99); opacity: 0; }
}
:root[data-motion='soft'] .aj-enter-active, :root[data-motion='soft'] .aj-leave-active { transition: opacity 0.18s; }
:root[data-motion='soft'] .aj-enter-from, :root[data-motion='soft'] .aj-leave-to { transform: none; opacity: 0; }
@media (pointer: coarse) {
  .fallback-btn { min-height: 44px; }
}
</style>
