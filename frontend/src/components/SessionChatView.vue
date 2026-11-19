<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { plainPreview } from '../lib/preview'
import { estadoEfectivo } from '../lib/fondo'
import { groupThread, type IndexedItem } from '../lib/transcript'
import { BLOCKED_REPLY } from '../lib/reply'
import { abrirEnPc } from '../state/app'
import { irAPcAviso, irAPcEnviando, irAPcSesion } from '../state/irAPc'
import { debeAutofocoAlAbrir, estaEditando } from '../lib/autofocoChat'
import { useSaltoMensaje } from './useSaltoMensaje'
import { composerRequest, dlg } from '../state/dialogo'
import { activeId, atenderSesion, chat, closeSessionChat, coldLink, currentSession, discardPending, loadOlder, openSessionId, retryLoad, retryPending, sendFromSession, settledIdx, threadItems } from '../state/session'
import { resizeAction } from '../lib/pegado'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import ViewHeader from './ViewHeader.vue'
import LogoLoader from './LogoLoader.vue'
import SessionComposer from './SessionComposer.vue'
import PreguntasDock from './PreguntasDock.vue'
import { dockHold, pendientes } from '../lib/stepper'
import type { LoteDock } from '../lib/dock'
import CompactDivider from './CompactDivider.vue'
import DialogCard from './DialogCard.vue'
import PedidosPestanaChat from './PedidosPestanaChat.vue'
import PinSheet from './PinSheet.vue'
import SessionMessage from './SessionMessage.vue'
import SubagentesStrip from './SubagentesStrip.vue'
import { nudgeSubagentes, stopSubagentes, subagentes, watchSubagentes } from '../state/subagentes'
import StatusLine from './StatusLine.vue'
import StatusPill from './StatusPill.vue'
import ToolGroup from './ToolGroup.vue'
import ChatFotos from './ChatFotos.vue'
import CambiosView from './CambiosView.vue'
import { cambios, cargarCambios, limpiarCambios } from '../state/cambios'
import { esSesionTerminal, esTerminalPropia } from '../lib/terminalPropia'
import { abrirVivo, loadTerminalConfig, vivoHabilitado } from '../state/terminalVivo'
import { tconfig } from '../state/terminalActions'

const props = defineProps<{ desktop: boolean }>()

const NOSWIPE = '.md-table, .md-code, textarea, input, [data-noswipe]'
const QUIET_TAIL = 8
const NEAR = 80

const root = ref<HTMLElement | null>(null)
const scroller = ref<HTMLElement | null>(null)
const content = ref<HTMLElement | null>(null)
const sentinel = ref<HTMLElement | null>(null)
const stick = ref(true)
const showJump = ref(false)
const baseline = ref(-1)

const cur = computed(() => currentSession())
const agent = computed(() => cur.value?.agent ?? null)
const status = computed(() => (agent.value ? estadoEfectivo(agent.value) : chat.head.status))
const title = computed(() => plainPreview(agent.value?.title ?? chat.head.title) || plainPreview(agent.value?.doing ?? '') || 'Sesión')
const where = computed(() => (cur.value ? [cur.value.ws.label, cur.value.tab.label].filter(Boolean).join(' · ') : ''))
const paneId = computed(() => agent.value?.pane_id || chat.head.paneId || '')
const showIrAPc = computed(() => esSesionTerminal(paneId.value) && !!openSessionId.value)
const avisoIrAPc = computed(() => (irAPcAviso.value && irAPcAviso.value.sid === openSessionId.value ? irAPcAviso.value : null))
const showVivo = computed(() => esTerminalPropia(paneId.value) && vivoHabilitado.value)
const blocked = computed(() => status.value === 'blocked')
const answerable = computed(() => dlg.view?.tipo === 'permiso' || dlg.view?.tipo === 'pregunta')
const working = computed(() => status.value === 'working')
const label = computed(() => `${title.value.slice(0, 150)} (${paneId.value})`)

const waiting = computed(() => !chat.loaded && !chat.error && !chat.missing)
const entries = computed(() => groupThread(threadItems.value))
const lastKey = computed(() => entries.value[entries.value.length - 1]?.key)

const quiet = (item: IndexedItem) => item.idx <= baseline.value || settledIdx.has(item.idx)

const pendingItems = computed(() =>
  chat.pending.map((p) => {
    const paths = p.files.map((f) => `/uploads/${f.id}`)
    const text = p.text
      ? `${p.text}${paths.map((x) => ` (Adjunto: ${x})`).join('')}`
      : paths.length
        ? `Te paso ${paths.join(', ')}`
        : ''
    return { p, item: { kind: 'user', text, name: '', summary: '', ts: '', idx: -1 } as IndexedItem }
  }),
)

// Reply that followed each claude message, so an option card knows it was answered.
const answers = computed(() => {
  const out = new Map<number, string>()
  let next: string | null = chat.pending.length ? chat.pending[chat.pending.length - 1].text || '(archivo)' : null
  for (let i = threadItems.value.length - 1; i >= 0; i--) {
    const it = threadItems.value[i]
    if (it.kind === 'user') next = it.text
    else if (it.kind === 'claude' && next !== null) out.set(it.idx, next)
  }
  return out
})
const pickOption = (text: string) => sendFromSession(paneId.value, label.value, text, [])
const preguntas = ref<InstanceType<typeof PreguntasDock> | null>(null)
const focusComposer = () => {
  if (preguntas.value?.release()) return
  root.value?.querySelector<HTMLTextAreaElement>('.composer textarea')?.focus()
}
// Questions of the last message, while nothing was sent after it.
const pend = computed(() => {
  if (!chat.loaded) return null
  const items = threadItems.value
  for (let i = items.length - 1; i >= 0; i--) {
    const it = items[i]
    if (it.kind !== 'claude' && it.kind !== 'user') continue
    return pendientes([{ id: String(it.idx), assistant: it.kind === 'claude', text: it.text }], chat.pending.length > 0)
  }
  return null
})
const lotes = computed<LoteDock[]>(() => (pend.value ? [{ key: `s:${openSessionId.value || paneId.value}`, sig: pend.value.sig, questions: pend.value.questions }] : []))
watch(composerRequest, () => nextTick(focusComposer))
const punteroFino = window.matchMedia('(hover: hover) and (pointer: fine)')
const autofoco = () => {
  if (!debeAutofocoAlAbrir({ desktop: props.desktop, punteroFino: punteroFino.matches, editando: estaEditando(document.activeElement) })) return
  root.value?.querySelector<HTMLTextAreaElement>('.composer textarea')?.focus({ preventScroll: true })
}
watch(openSessionId, () => nextTick(autofoco))

const verCambios = ref(false)
const cambiosN = computed(() => (cambios.sid === openSessionId.value && cambios.data?.repo ? cambios.data.archivos.length : null))
watch(
  openSessionId,
  (id) => {
    verCambios.value = false
    if (id) cargarCambios(id)
    else limpiarCambios()
  },
  { immediate: true },
)

useSaltoMensaje({ scroller, mensajes: computed(() => entries.value.length), sid: openSessionId, cargado: computed(() => chat.loaded), verCambios, stick, toBottom })

const nearBottom = () => {
  const el = scroller.value
  return !el || el.scrollHeight - el.scrollTop - el.clientHeight < NEAR
}

let lastTop = 0
function onScroll() {
  const el = scroller.value
  if (!el) return
  if (nearBottom()) {
    stick.value = true
    showJump.value = false
  } else if (el.scrollTop < lastTop - 2) {
    stick.value = false
  }
  lastTop = el.scrollTop
}

function toBottom(smooth = false) {
  const el = scroller.value
  if (!el) return
    el.scrollTo({ top: el.scrollHeight, behavior: smooth && !isSoft() ? 'smooth' : 'auto' })
  stick.value = true
  showJump.value = false
}

let ro: ResizeObserver | null = null
let io: IntersectionObserver | null = null

function watchSentinel() {
  if (!io || !sentinel.value) return
  io.unobserve(sentinel.value)
  io.observe(sentinel.value)
}

function onEsc(e: KeyboardEvent) {
  if (e.key !== 'Escape' || e.defaultPrevented || !props.desktop || !openSessionId.value) return
  if (document.querySelector('[aria-modal="true"]')) return
  const t = e.target as HTMLElement | null
  if (t?.closest?.('textarea, input, select, [contenteditable="true"]')) return
  e.preventDefault()
  closeSessionChat()
}

const abriendoEnPc = ref(false)
const avisoPc = ref<string | null>(null)
let avisoPcTimer: ReturnType<typeof setTimeout> | undefined

function mostrarAvisoPc(texto: string) {
  avisoPc.value = texto
  clearTimeout(avisoPcTimer)
  avisoPcTimer = setTimeout(() => (avisoPc.value = null), 3000)
}

function abrirTerminalConPin() {
  abrirVivo(paneId.value, title.value, { pedirPin: true })
}

async function pedirAbrirEnPc() {
  if (abriendoEnPc.value || !paneId.value) return
  abriendoEnPc.value = true
  try {
    const r = await abrirEnPc(paneId.value, title.value)
    mostrarAvisoPc(r.ok ? 'Listo, se abrió en la PC' : 'No hay ninguna Colmena abierta en la PC')
  } catch {
    mostrarAvisoPc('No pude abrirla en la PC')
  } finally {
    abriendoEnPc.value = false
  }
}

onMounted(() => {
  if (!tconfig.value) void loadTerminalConfig()
  void nextTick(autofoco)
  window.addEventListener('keydown', onEsc)
  ro = new ResizeObserver((es) => {
    const act = resizeAction(stick.value, es.map((e) => e.target), content.value)
    if (act === 'bottom') toBottom()
    else if (act === 'jump' && chat.loaded) showJump.value = true
  })
  if (content.value) ro.observe(content.value)
  if (scroller.value) ro.observe(scroller.value)
  io = new IntersectionObserver(
    (es) => {
      if (es.some((e) => e.isIntersecting) && chat.loaded && chat.before !== null) void loadOlder()
    },
    { root: scroller.value, rootMargin: '240px 0px 0px 0px' },
  )
  watchSentinel()
  enter()
})
onBeforeUnmount(() => {
  clearTimeout(avisoPcTimer)
  window.removeEventListener('keydown', onEsc)
  stopSubagentes()
  ro?.disconnect()
  io?.disconnect()
})

watch(
  threadItems,
  async (next, prev) => {
    const el = scroller.value
    if (!el) return
    const prepended = !!prev.length && !!next.length && next[0].idx < prev[0].idx
    const h = el.scrollHeight
    const top = el.scrollTop
    await nextTick()
    if (prepended) {
      el.scrollTop = top + (el.scrollHeight - h)
      lastTop = el.scrollTop
      watchSentinel()
    }
  },
  { flush: 'pre' },
)

watch(
  () => chat.loaded,
  async (on) => {
    if (!on) return
    const last = threadItems.value[threadItems.value.length - 1]
    baseline.value = (last?.idx ?? -1) - QUIET_TAIL
    await nextTick()
    toBottom()
    watchSentinel()
  },
  { immediate: true },
)

watch(
  openSessionId,
  (id) => (id ? watchSubagentes(id, () => working.value) : stopSubagentes()),
  { immediate: true },
)
watch(working, (on) => on && nudgeSubagentes())

watch(activeId, () => {
  baseline.value = -1
  stick.value = true
  showJump.value = false
})

watch(
  () => chat.pending.length,
  (n, o) => n > o && nextTick(() => toBottom(true)),
)

// ---------- entrance, and swipe back on touch ----------
const { run } = useGsap()

function enter() {
  const el = root.value
  if (!el || isSoft() || coldLink.value) return
  const q = gsap.utils.selector(el)
  run(() => {
    // Valores finales explícitos: si se leen de la hoja de estilos en medio de una transición, quedan transparentes.
    gsap.fromTo(q('.head > *'), { y: -10, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: 'power3.out', stagger: 0.05, delay: 0.1, clearProps: 'opacity,transform' })
    gsap.fromTo(q('.dock'), { y: 26, opacity: 0 }, { y: 0, opacity: 1, duration: 0.6, ease: 'power3.out', delay: 0.15, clearProps: 'opacity,transform' })
  })
}

let g: { id: number; x0: number; y0: number; lock: 'x' | 'y' | null; w: number; lx: number; lt: number; v: number } | null = null

function onAtender() {
  atenderSesion()
}

function onPointerDown(e: PointerEvent) {
  onAtender()
  onDown(e)
}

function onDown(e: PointerEvent) {
  if (props.desktop || e.pointerType === 'mouse' || !root.value) return
  if ((e.target as Element).closest(NOSWIPE)) return
  g = { id: e.pointerId, x0: e.clientX, y0: e.clientY, lock: null, w: root.value.clientWidth, lx: e.clientX, lt: e.timeStamp, v: 0 }
}
function onMove(e: PointerEvent) {
  if (!g || e.pointerId !== g.id || !root.value) return
  const dx = e.clientX - g.x0
  const dy = e.clientY - g.y0
  if (!g.lock) {
    if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return
    g.lock = Math.abs(dx) > Math.abs(dy) * 1.4 && dx > 0 ? 'x' : 'y'
    if (g.lock === 'x') root.value.setPointerCapture(e.pointerId)
  }
  if (g.lock !== 'x') return
  const dt = Math.max(1, e.timeStamp - g.lt)
  g.v = (e.clientX - g.lx) / dt
  g.lx = e.clientX
  g.lt = e.timeStamp
  gsap.set(root.value, { x: Math.max(0, dx) })
}
function onUp(e: PointerEvent) {
  const s = g
  g = null
  const el = root.value
  if (!s || !el || s.lock !== 'x') return
  const dx = Math.max(0, e.clientX - s.x0)
  const go = dx > s.w * 0.35 || s.v > 0.6
  if (isSoft()) {
    gsap.set(el, { x: 0 })
    if (go) closeSessionChat()
    return
  }
  if (go) {
    haptic(8)
    gsap.to(el, { x: s.w, duration: 0.28, ease: 'power3.out', onComplete: closeSessionChat })
  } else {
    gsap.to(el, { x: 0, duration: 0.25, ease: 'power3.out', clearProps: 'transform' })
  }
}

</script>

<template>
  <section
    ref="root"
    class="sess"
    :class="{ desktop }"
    aria-label="Chat de la sesión"
    @pointerdown="onPointerDown"
    @keydown="onAtender"
    @wheel.passive="onAtender"
    @touchstart.passive="onAtender"
    @pointermove="onMove"
    @pointerup="onUp"
    @pointercancel="onUp"
  >
    <nav v-if="desktop" class="crumb" aria-label="Dónde estás">
      <button type="button" class="crumb-back hit" title="Volver (Esc)" @click="closeSessionChat">
        <Icon name="back" :size="14" /><span>Volver</span>
      </button>
      <ol class="crumb-path">
        <li aria-current="page" class="crumb-here">{{ title }}</li>
      </ol>
    </nav>
    <ViewHeader compact class="head" :sticky="true">
      <template #back>
        <button
          v-if="!desktop"
          type="button"
          class="btn btn-back back"
          aria-label="Volver"
          @click="closeSessionChat"
        >
          <Icon name="back" :size="19" />
        </button>
      </template>
      <template #title>
        <div class="who">
          <h1 :title="title">{{ title }}</h1>
          <p v-if="where" class="where mono">{{ where }}</p>
        </div>
      </template>
      <template #actions>
        <StatusPill v-if="status !== 'unknown'" :status="status" small />
        <button
          v-if="openSessionId"
          type="button"
          class="term-act"
          :class="{ on: verCambios }"
          aria-label="Ver cambios de la sesión"
          :aria-pressed="verCambios"
          @click="verCambios = !verCambios"
        >
          <Icon name="branch" :size="14" /><span>Cambios</span><span v-if="cambiosN" class="cnt mono">{{ cambiosN }}</span>
        </button>
        <button
          v-if="showVivo"
          type="button"
          class="term-act vivo"
          aria-label="Abrir terminal en vivo"
          @click="abrirTerminalConPin"
        >
          <Icon name="terminal" :size="14" /><span>Abrir terminal</span>
        </button>
        <button
          v-if="showVivo && !desktop"
          type="button"
          class="term-act pc"
          aria-label="Abrir en la PC"
          :disabled="abriendoEnPc"
          :aria-busy="abriendoEnPc"
          @click="pedirAbrirEnPc"
        >
          <Icon name="monitor" :size="14" /><span>Abrir en la PC</span>
        </button>
        <button
          v-if="showIrAPc"
          type="button"
          class="term-act pc"
          aria-label="Ir a PC"
          title="Abre una terminal en la notebook"
          :disabled="!!irAPcEnviando[openSessionId!]"
          :aria-busy="!!irAPcEnviando[openSessionId!]"
          @click="irAPcSesion(openSessionId!)"
        >
          <Icon name="terminal" :size="14" /><span>Ir a PC</span>
        </button>
      </template>
    </ViewHeader>
    <p v-if="avisoIrAPc" class="pc-aviso mono" :class="{ err: !avisoIrAPc.ok }" role="status">{{ avisoIrAPc.texto }}</p>
    <p v-if="avisoPc" class="pc-aviso mono" role="status">{{ avisoPc }}</p>
    <StatusLine v-if="chat.loaded" class="statline" :line="chat.statusLine" :ctx="agent?.ctx ?? null" />

    <CambiosView v-if="verCambios && openSessionId" :sid="openSessionId" :desktop="desktop" />

    <div v-show="!verCambios" ref="scroller" class="scroll" @scroll.passive="onScroll">
      <div ref="content" class="thread">
        <div ref="sentinel" class="sentinel" aria-hidden="true">
          <span v-if="chat.loadingOlder" class="older mono"><i class="spin" /> Cargando mensajes anteriores</span>
        </div>

        <div v-if="chat.missing" class="state">
          <p class="kicker mono">sin rastro</p>
          <h2>Esa sesión ya no está en el tablero</h2>
          <p class="sub">{{ desktop ? 'Se cerró o todavía no la veo. Elegí otra en el tablero.' : 'Se cerró o todavía no la veo. Volvé al tablero y abrí otra.' }}</p>
          <button class="btn" @click="closeSessionChat"><Icon name="back" :size="14" /> Volver</button>
        </div>

        <div v-else-if="chat.error" class="state">
          <p class="kicker mono err">no pude leerla</p>
          <h2>{{ chat.error }}</h2>
          <button class="btn hit" @click="retryLoad"><Icon name="refresh" :size="14" /> Reintentar</button>
        </div>

        <template v-else-if="chat.loaded">
          <p v-if="!entries.length" class="blank mono">Todavía no escribió nada.</p>
          <template v-for="e in entries" :key="e.key">
            <ToolGroup v-if="e.type === 'tools'" :tools="e.tools" :live="working && e.key === lastKey" :quiet="quiet(e.tools[e.tools.length - 1])" />
            <ChatFotos v-else-if="e.item.kind === 'imagenes' && e.item.fotos?.length" :fotos="e.item.fotos" :quiet="quiet(e.item)" />
            <CompactDivider v-else-if="e.item.kind === 'compact'" :item="e.item" :quiet="quiet(e.item)" />
            <SessionMessage
              v-else
              :item="e.item"
              :quiet="quiet(e.item)"
              :answer="answers.get(e.item.idx)"
              :session-id="openSessionId ?? undefined"
              :session-nombre="title"
              :locked="blocked"
              @pick="pickOption"
              @other="focusComposer"
            />
          </template>
          <div v-for="{ p, item } in pendingItems" :key="p.key" class="pend" :class="p.phase">
            <SessionMessage :item="item" />
            <p v-if="p.phase === 'failed'" class="pend-err" role="alert">
              <Icon name="warn" :size="12" /> <span>{{ p.error || 'No se envió' }}</span>
              <button class="hit" @click="retryPending(p)">Reintentar</button>
              <button class="hit" @click="discardPending(p)">Descartar</button>
            </p>
            <p v-else-if="p.queued" class="pend-queue" role="status">En cola</p>
          </div>
          <DialogCard v-if="openSessionId" :session-id="openSessionId" :status="status" :tab-id="cur?.tab.id" :vivo="showVivo" @vivo="abrirTerminalConPin" />
          <PedidosPestanaChat v-if="openSessionId" :session-id="openSessionId" />
          <Transition name="work">
            <p v-if="working && chat.loaded" class="working mono" role="status">
              <span class="bars" aria-hidden="true"><i /><i /><i /></span> Trabajando
            </p>
          </Transition>
        </template>
      </div>
    </div>

    <Transition name="load">
      <LogoLoader v-if="waiting" class="loading" />
    </Transition>

    <PinSheet />

    <div v-show="!verCambios" class="dock">
      <Transition name="jump">
        <button v-if="showJump" class="jump hit" aria-label="Ir al final" @click="toBottom(true)"><Icon name="down" :size="14" /> Ir al final</button>
      </Transition>
      <Transition name="rise">
        <p v-if="blocked && !answerable" class="banner" role="status"><Icon name="lock" :size="14" /> {{ BLOCKED_REPLY }}</p>
      </Transition>
      <SubagentesStrip v-if="chat.loaded" :key="openSessionId || ''" :items="subagentes" />
      <PreguntasDock
        v-if="paneId"
        ref="preguntas"
        :lotes="lotes"
        :chat-key="`s:${openSessionId || paneId}`"
        :hold="dockHold({ working, blocked })"
        :active="true"
        :send="(_l: LoteDock, text: string) => pickOption(text)"
      >
        <SessionComposer :pane-id="paneId" :label="label" :name="title" :blocked="blocked" :working="working" />
      </PreguntasDock>
    </div>
  </section>
</template>

<style scoped>
.sess {
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
  height: 100%;
  background: var(--bg);
  touch-action: pan-y;
}
.who-titles {
  min-width: 0;
}
.head :deep(.vh-start) {
  min-width: 0;
  flex: 1;
}
.head :deep(.vh-titles) {
  min-width: 0;
}
.crumb {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 8px var(--gutter) 0;
  font-size: var(--t-md);
  color: var(--text-3);
}
.crumb-back {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px 0 7px;
  border-radius: 8px;
  color: var(--text-2);
  font-weight: 550;
  box-shadow: inset 0 0 0 1px var(--line);
  transition: background 0.2s, color 0.2s, translate 0.35s var(--spring);
}
.crumb-back:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.crumb-back:hover :deep(svg) {
  translate: -2px 0;
  transition: translate 0.35s var(--spring);
}
.crumb-path {
  display: flex;
  align-items: center;
  min-width: 0;
  margin: 0;
  padding: 0;
  list-style: none;
}
.crumb-path li {
  display: flex;
  align-items: center;
  min-width: 0;
}
.crumb-path li + li::before {
  content: '›';
  margin: 0 7px;
  color: var(--text-4);
}
.crumb-here {
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.desktop .statline {
  padding-left: var(--gutter);
}
.desktop .crumb + .head {
  padding-top: 8px;
}
.who {
  min-width: 0;
}
h1 {
  margin: 0;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 15px;
  letter-spacing: -0.01em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.where {
  margin: 1px 0 0;
  font-size: 11px;
  color: var(--text-4);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.term-act {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 11px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: color 0.2s, background 0.2s, box-shadow 0.2s, opacity 0.2s, scale 0.35s var(--spring);
}
.term-act:hover:not(:disabled) {
  color: var(--text);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.term-act.on {
  color: var(--text);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.term-act .cnt {
  font-size: 11px;
  color: var(--text-3, var(--text-2));
}
.term-act:active:not(:disabled) {
  scale: var(--press-scale);
}
.term-act:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.term-act.vivo {
  color: var(--text);
  background: color-mix(in srgb, var(--accent-soft) 70%, transparent);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.pc-aviso.err {
  color: var(--danger);
}
.pc-aviso {
  margin: 0;
  padding: 6px 14px;
  font-size: var(--t-sm);
  color: var(--text-3);
  text-align: center;
  background: var(--accent-soft);
  border-bottom: 1px solid var(--line);
}
@media (max-width: 1023px) {
  .head {
    flex-wrap: wrap;
    row-gap: 6px;
  }
  .head :deep(.vh-start) {
    flex: 1 1 100%;
  }
  .head :deep(.vh-actions) {
    flex: 1 1 100%;
    min-width: 0;
    justify-content: flex-start;
    overflow-x: auto;
    overscroll-behavior-x: contain;
    scrollbar-width: none;
  }
  .head :deep(.vh-actions)::-webkit-scrollbar {
    display: none;
  }
  .who h1 {
    display: -webkit-box;
    -webkit-box-orient: vertical;
    -webkit-line-clamp: 2;
    line-clamp: 2;
    white-space: normal;
    overflow-wrap: anywhere;
  }
  .term-act span {
    display: none;
  }
  .term-act {
    width: 34px;
    padding: 0;
    justify-content: center;
  }
}

.scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  overflow-anchor: none;
}
.thread {
  width: 100%;
  margin: 0 auto;
  padding: 4px var(--gutter) 24px;
  box-sizing: border-box;
}
.thread :deep(.msg),
.thread :deep(.state),
.thread :deep(.blank),
.thread :deep(.pend),
.thread :deep(.working),
.thread :deep(.tool-group),
.thread :deep(.fotos),
.thread :deep(.compact-div),
.thread :deep(.dialog-card),
.thread :deep(.pedidos-chat) {
  max-width: var(--chat-max);
  margin-inline: auto;
  width: 100%;
}
.sentinel {
  height: 36px;
  display: grid;
  place-items: center;
}
.older {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
  color: var(--text-4);
}
.spin {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 1.5px solid var(--accent);
  border-right-color: transparent;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}

.state {
  padding: 10vh 0 24px;
}
.kicker {
  margin: 0 0 10px;
  font-size: 11px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--accent);
}
.kicker.err {
  color: var(--danger);
}
.state h2 {
  margin: 0 0 8px;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: clamp(22px, 3.4vw, 30px);
  letter-spacing: -0.03em;
  line-height: 1.1;
}
.sub {
  margin: 0 0 20px;
  color: var(--text-3);
  max-width: 380px;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 34px;
  padding: 0 14px;
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: color 0.2s, background 0.2s, scale 0.35s var(--spring);
}
.btn:hover {
  color: var(--text);
  background: var(--surface-hover);
}
.btn:active {
  scale: var(--press-scale);
}
.blank {
  margin: 8vh 0;
  text-align: center;
  font-size: 12px;
  color: var(--text-4);
}

.pend.sending :deep(.bubble),
.pend.sent :deep(.bubble) {
  opacity: 0.72;
}
.pend.failed :deep(.bubble) {
  border-color: var(--danger);
}
.pend-err {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 6px;
  margin: 0 0 8px;
  font-size: 12px;
  color: var(--danger);
}
.pend-err span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.pend-err button {
  flex: none;
  padding: 2px 4px;
  border-radius: 6px;
  color: var(--text-2);
  text-decoration: underline;
  text-underline-offset: 2px;
}
.pend-queue {
  margin: 0 0 8px;
  text-align: right;
  font-size: var(--t-sm);
  color: var(--text-4);
}
.working {
  display: flex;
  align-items: center;
  gap: 9px;
  margin: 10px 0 0 26px;
  font-size: var(--t-sm);
  letter-spacing: 0.04em;
  color: var(--accent);
}
.working::after {
  content: '';
  animation: ellipsis 1.4s steps(4, end) infinite;
}
@keyframes ellipsis {
  0% { content: ''; }
  25% { content: '.'; }
  50% { content: '..'; }
  75% { content: '...'; }
}
.bars {
  display: inline-flex;
  align-items: flex-end;
  gap: 2px;
  height: 12px;
}
.bars i {
  width: 3px;
  height: 100%;
  border-radius: 1px;
  background: currentColor;
  transform-origin: bottom;
  animation: bar 1.1s var(--ease-in-out) infinite;
}
.bars i:nth-child(2) { animation-delay: 0.15s; }
.bars i:nth-child(3) { animation-delay: 0.3s; }
@keyframes bar {
  0%, 100% { transform: scaleY(0.3); }
  50% { transform: scaleY(1); }
}
:root[data-motion='soft'] .bars i,
:root[data-motion='soft'] .working::after { animation: none; }
.work-enter-active { transition: opacity 0.3s, transform 0.5s var(--spring); }
.work-leave-active { transition: opacity 0.15s; }
.work-enter-from { opacity: 0; transform: translateY(6px); }
.work-leave-to { opacity: 0; }

.loading {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}
.load-leave-active { transition: opacity 0.3s var(--ease-out); }
.load-leave-to { opacity: 0; }

.dock {
  position: relative;
  width: 100%;
  max-width: var(--read-max);
  margin: 0 auto;
  padding: 8px var(--gutter) max(14px, env(safe-area-inset-bottom));
  box-sizing: border-box;
}
@media (max-width: 1023px) {
  .dock { padding: 6px var(--gutter) max(10px, env(safe-area-inset-bottom)); }
}
.dock :deep(.subs) {
  max-width: 100%;
}
.kb-open .dock {
  padding-bottom: 8px;
}
.banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 8px;
  padding: 9px 12px;
  border-radius: 12px;
  font-size: 13px;
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--st-blocked) 28%, transparent);
}
.rise-enter-active { transition: opacity 0.3s, transform 0.5s var(--spring); }
.rise-leave-active { transition: opacity 0.15s; }
.rise-enter-from { opacity: 0; transform: translateY(8px) scale(0.98); }
.rise-leave-to { opacity: 0; }
.jump {
  position: absolute;
  left: 50%;
  top: -40px;
  transform: translateX(-50%);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 30px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  font-size: 12px;
  background: var(--surface-2);
  box-shadow: var(--shadow-pop);
  color: var(--text-2);
}
.jump-enter-active { transition: opacity 0.2s, transform 0.45s var(--spring); }
.jump-leave-active { transition: opacity 0.15s, transform 0.2s; }
.jump-enter-from, .jump-leave-to { opacity: 0; transform: translate(-50%, 8px); }
</style>
