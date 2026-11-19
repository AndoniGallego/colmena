import { computed, reactive, ref, shallowRef, watch } from 'vue'
import { ApiError, type AgentStatus, type StatusLine } from '../api/types'
import { findSession, mergeTail, parseDeepLink, parseDialogFlag, prependOlder, sentArrived, type IndexedItem, type ThreadState } from '../lib/transcript'
import type { AttachKind } from '../lib/attachments'
import { auth, boardState, getTranscript, inOrder, markSeen, postMensaje, sessionEvent } from './app'
import { estaALaVista } from '../lib/aLaVista'
import { shouldMarkSeen } from '../lib/seen'
import { newId } from '../lib/reply'
import { desktop } from '../lib/viewport'
import { informarMirando } from '../api/http'

export interface PendingFile {
  id: string
  name: string
  kind: AttachKind
  preview?: string
}

export interface Pending {
  key: string
  id: string
  paneId: string
  label: string
  /** Sent while the session was mid-turn: it waits in Claude Code's input queue until the turn ends. */
  queued: boolean
  text: string
  files: PendingFile[]
  baseIdx: number
  phase: 'sending' | 'sent' | 'failed'
  error?: string
}

interface SessionChat {
  loaded: boolean
  loadingOlder: boolean
  error: string | null
  missing: boolean
  before: number | null
  head: { title: string; status: AgentStatus; paneId: string }
  statusLine: StatusLine | null
  pending: Pending[]
}

const PAGE = 60
/** Cada tantos refrescos con cola parcial se pide la página completa (un lib_id tardío fuera del solape no queda viejo). */
export const REFRESCOS_PARCIALES = 10
const PENDING_TTL_MS = 90_000
const SEGUIMIENTO_MS = 1500

let seguimientoTimer: ReturnType<typeof setTimeout> | null = null

/** Refresca el transcript ya y otra vez tras un margen por si el backend aún no escribió la cola. */
export function refrescarConSeguimiento(
  refreshFn: () => void | Promise<void> = refreshTail,
  getActiveId: () => string | null = () => activeId.value,
) {
  const idAtCall = getActiveId()
  if (!idAtCall) return
  void refreshFn()
  if (seguimientoTimer) clearTimeout(seguimientoTimer)
  seguimientoTimer = setTimeout(() => {
    seguimientoTimer = null
    const idNow = getActiveId()
    if (!idNow || idNow !== idAtCall) return
    void refreshFn()
  }, SEGUIMIENTO_MS)
}

export const openSessionId = ref<string | null>(null)
export const activeId = computed(() => openSessionId.value)
/** Arranque desde un deep link: la vista aparece ya armada, sin entradas animadas sobre el fondo vacío. */
export const coldLink = ref(false)
/** The push said this session is waiting on a dialog: its card opens in view, once. */
export const dialogoLink = ref(false)
/** Browser already animated the back gesture: the chat layer leaves without its own transition. */
export const cierreSinTransicion = ref(false)
export function terminarCierreSinTransicion() {
  cierreSinTransicion.value = false
}
/** Items that replaced an optimistic bubble: their views skip the entrance. */
export const settledIdx = new Set<number>()

export const chat = reactive<SessionChat>(blank())
export const threadItems = shallowRef<IndexedItem[]>([])

function blank(): SessionChat {
  return {
    loaded: false,
    loadingOlder: false,
    error: null,
    missing: false,
    before: null,
    head: { title: '', status: 'unknown', paneId: '' },
    statusLine: null,
    pending: [],
  }
}

let token = 0
let inflight: Promise<void> | null = null
let again = false
let pushed = false
let forzarCompleta = true
let parciales = 0
let seq = 0

let thread: ThreadState = { items: [], before: null }

/** Optimistic bubbles stashed while another session is on screen (in-memory only). */
const pendingBySession = new Map<string, Pending[]>()

/** @internal vitest */
export function clearPendingStashForTests() {
  pendingBySession.clear()
}

function removePendingEverywhere(entry: Pending) {
  chat.pending = chat.pending.filter((p) => p !== entry)
  for (const [sid, list] of pendingBySession) {
    const next = list.filter((p) => p !== entry)
    if (next.length === list.length) continue
    if (next.length) pendingBySession.set(sid, next)
    else pendingBySession.delete(sid)
  }
}

function stashPendingForSession(sessionId: string) {
  if (!chat.pending.length) return
  pendingBySession.set(sessionId, chat.pending.slice())
}

function restorePendingForSession(sessionId: string) {
  const stored = pendingBySession.get(sessionId)
  if (!stored?.length) return
  pendingBySession.delete(sessionId)
  const working = sessionWorking()
  for (const p of stored) {
    if (!working && p.queued) {
      p.queued = false
      if (p.phase === 'sent') expireLater(p)
    }
  }
  chat.pending.push(...stored)
}

function setThread(next: ThreadState) {
  thread = next
  threadItems.value = next.items
  chat.before = next.before
}

function reset() {
  token++
  inflight = null
  again = false
  forzarCompleta = true
  parciales = 0
  Object.assign(chat, blank())
  setThread({ items: [], before: null })
  settledIdx.clear()
}

function failure(e: unknown) {
  if (e instanceof ApiError && e.status === 404) {
    chat.missing = true
    chat.error = null
  } else {
    chat.error = e instanceof ApiError ? e.detail : 'No pude leer la sesión'
  }
}

function settlePending() {
  const items = thread.items
  const keep = (p: Pending) => {
    if (p.phase !== 'sent' || !sentArrived(items, p)) return true
    items.forEach((i) => i.kind === 'user' && i.idx > p.baseIdx && settledIdx.add(i.idx))
    return false
  }
  chat.pending = chat.pending.filter(keep)
}

export async function refreshTail(): Promise<void> {
  const id = activeId.value
  if (!id) return
  if (inflight) {
    again = true
    return inflight
  }
  const mine = token
  inflight = (async () => {
    try {
      const last = thread.items[thread.items.length - 1]
      const parcial = !forzarCompleta && !!last && parciales < REFRESCOS_PARCIALES - 1
      const page = await getTranscript(id, null, PAGE, parcial ? last.idx : null)
      if (mine !== token) return
      if (parcial) parciales++
      else {
        forzarCompleta = false
        parciales = 0
      }
      setThread(mergeTail(thread, page))
      chat.head = { title: page.title, status: page.status, paneId: page.pane_id }
      chat.statusLine = page.status_line
      chat.loaded = true
      chat.missing = false
      chat.error = null
      settlePending()
    } catch (e) {
      if (mine === token && !chat.loaded) failure(e)
    } finally {
      if (mine === token) inflight = null
    }
    if (mine === token && again) {
      again = false
      await refreshTail()
    }
  })()
  return inflight
}

export async function loadOlder(): Promise<void> {
  const id = activeId.value
  const before = thread.before
  if (!id || before === null || chat.loadingOlder) return
  const mine = token
  chat.loadingOlder = true
  try {
    const page = await getTranscript(id, before, PAGE)
    if (mine === token) setThread(prependOlder(thread, page))
  } catch {
    /* the sentinel stays, the next scroll retries */
  } finally {
    if (mine === token) chat.loadingOlder = false
  }
}

export function retryLoad() {
  chat.error = null
  chat.missing = false
  void refreshTail()
}

function writeUrl(id: string | null, mode: 'push' | 'replace') {
  const params = new URLSearchParams(location.search)
  if (id) params.set('session', id)
  else params.delete('session')
  params.delete('chat')
  params.delete('terminal')
  params.delete('dialogo')
  const query = params.toString()
  const url = location.pathname + (query ? `?${query}` : '')
  const state = id ? { orqSession: id } : null
  if (mode === 'push') history.pushState(state, '', url)
  else history.replaceState(state, '', url)
}

function show(id: string | null) {
  if (id) cierreSinTransicion.value = false
  openSessionId.value = id
}

watch(activeId, (id, prev) => {
  if (prev && chat.pending.length) stashPendingForSession(prev)
  reset()
  if (id) restorePendingForSession(id)
  if (id) void refreshTail()
}, { flush: 'sync' })

/** Desktop shows one conversation at a time in the right column; switching never stacks history entries. */
function select(id: string | null) {
  show(id)
  writeUrl(id, 'replace')
}

export function openSessionChat(id: string) {
  if (openSessionId.value === id) return
  if (desktop.value) return select(id)
  show(id)
  writeUrl(id, 'push')
  pushed = true
}

export function closeSessionChat() {
  if (!openSessionId.value) return
  if (desktop.value) {
    show(null)
    writeUrl(null, 'replace')
    return
  }
  if (pushed) {
    pushed = false
    history.back()
    return
  }
  show(null)
  writeUrl(null, 'replace')
}

// Only a link (a push, a shared URL) opens a session directly.
export function initSessionNav() {
  const link = parseDeepLink(location.search)
  if (link) {
    dialogoLink.value = parseDialogFlag(location.search)
    coldLink.value = true
    show(link)
    writeUrl(link, 'replace')
  }
  window.addEventListener('popstate', (e) => {
    pushed = false
    const id = typeof e.state?.orqSession === 'string' ? e.state.orqSession : null
    if (!id && (e as PopStateEvent & { hasUAVisualTransition?: boolean }).hasUAVisualTransition === true) cierreSinTransicion.value = true
    show(id)
  })
}

export function currentSession() {
  const board = boardState.value.board
  return openSessionId.value ? findSession(board, openSessionId.value) : null
}

const expiring = new WeakSet<Pending>()

function expireLater(entry: Pending) {
  if (expiring.has(entry)) return
  expiring.add(entry)
  setTimeout(() => removePendingEverywhere(entry), PENDING_TTL_MS)
}

const sessionWorking = () => (currentSession()?.agent.status ?? chat.head.status) === 'working'

async function deliver(entry: Pending) {
  entry.phase = 'sending'
  entry.error = undefined
  const files = entry.files.map((f) => f.id)
  const r = await inOrder(entry.paneId, () => postMensaje(entry.paneId, entry.label, entry.text, files, entry.id))
  if (!r.ok) {
    entry.phase = 'failed'
    entry.error = r.error
    entry.queued = false
    if (r.uncertain) entry.id = newId()
    return
  }
  entry.phase = 'sent'
  if (r.enCola !== undefined) entry.queued = r.enCola
  if (!entry.queued) expireLater(entry)
  void refreshTail()
}

/** Never waits for earlier messages: each one gets its own bubble and id, and the pane's chain keeps the order. */
export function sendFromSession(paneId: string, label: string, text: string, files: PendingFile[]): Pending {
  const last = thread.items[thread.items.length - 1]
  const entry: Pending = reactive({
    key: `p${Date.now().toString(36)}${seq++}`,
    id: newId(),
    paneId,
    label,
    queued: sessionWorking(),
    text: text.trim(),
    files,
    baseIdx: last?.idx ?? -1,
    phase: 'sending',
  })
  chat.pending.push(entry)
  void deliver(entry)
  return entry
}

export function retryPending(entry: Pending) {
  if (entry.phase === 'failed') void deliver(entry)
}

export function discardPending(entry: Pending) {
  removePendingEverywhere(entry)
}

watch(sessionEvent, (e) => {
  if (e && e.session_id === activeId.value) void refreshTail()
})

// Lo que llegó mientras no había conexión no viene como evento "session": al reconectar se pide la cola.
watch(() => boardState.value.connection, (now, before) => {
  if (now === 'live' && before !== 'live' && activeId.value) {
    forzarCompleta = true
    void refreshTail()
  }
})

/** Claude Code toma lo encolado dentro del turno en curso, así que cualquier entrada o salida de "working" lo libera. */
export function releaseQueued(status: string | undefined, prev: string | undefined) {
  if (!status || !prev || status === prev || (status !== 'working' && prev !== 'working')) return
  chat.pending.forEach((p) => {
    if (!p.queued) return
    p.queued = false
    if (p.phase === 'sent') expireLater(p)
  })
}

watch(
  () => currentSession()?.agent.status ?? chat.head.status,
  (status, prev) => {
    if (activeId.value && status && prev && status !== prev) refrescarConSeguimiento()
    releaseQueued(status, prev)
  },
)

watch(auth, (a) => {
  if (a === 'ready' && activeId.value && !chat.loaded) retryLoad()
})

export const sesionAtendida = ref<{ id: string; n: number } | null>(null)

export function atenderSesion(): void {
  const id = openSessionId.value
  if (!id) return
  const visible = estaALaVista(typeof document === 'undefined' ? undefined : document, desktop.value)
  if (!visible) return
  const agent = currentSession()?.agent
  if (shouldMarkSeen({ unread: agent?.unread, status: agent?.status, sessionOpen: true, visible: true })) markSeen(id)
  const prev = sesionAtendida.value
  sesionAtendida.value = { id, n: prev?.id === id ? prev.n + 1 : 1 }
}

watch(openSessionId, (id) => {
  informarMirando(id)
  if (id) atenderSesion()
})
