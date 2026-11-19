import { reactive, shallowRef } from 'vue'
import { ApiError, type TerminalEstado, type TerminalMotivo } from '../api/types'
import type { AnsiLine } from '../lib/ansi'
import { nuevoCacheAnsi, parseAnsiLineas } from '../lib/ansi'
import { getTerminalSalida } from './app'
import { desktop } from '../lib/viewport'

export const POLL_MS = 1500
export const BACKOFF = [3000, 6000, 12000]
export const BACKOFF_MAX = 15000

export interface TerminalView {
  paneId: string
  rev: string
  loaded: boolean
  truncado: boolean
  cwd: string
  proceso: string
  estado: TerminalEstado
  puedeEscribir: boolean | null
  motivo: TerminalMotivo | null
  error: string | null
  gone: string | null
  paused: boolean
}

export const openTerminalId = shallowRef<string | null>(null)
export const view = reactive<TerminalView>(blank(''))
const cacheAnsi = nuevoCacheAnsi()
export const lines = shallowRef<AnsiLine[]>([])

function blank(paneId: string): TerminalView {
  return { paneId, rev: '', loaded: false, truncado: false, cwd: '', proceso: '', estado: 'desconocido', puedeEscribir: null, motivo: null, error: null, gone: null, paused: false }
}

let timer: ReturnType<typeof setTimeout> | undefined
let ctrl: AbortController | null = null
let failures = 0
let active: string | null = null

const visible = () => typeof document === 'undefined' || document.visibilityState === 'visible'

function schedule(ms: number) {
  clearTimeout(timer)
  if (!active || !visible()) return
  timer = setTimeout(() => void poll(), ms)
}

export async function poll(): Promise<void> {
  const paneId = active
  if (!paneId || !visible()) return
  ctrl?.abort()
  const mine = (ctrl = new AbortController())
  try {
    const out = await getTerminalSalida(paneId, view.rev, mine.signal)
    if (active !== paneId || mine.signal.aborted) return
    failures = 0
    view.error = null
    view.cwd = out.cwd || view.cwd
    view.proceso = out.proceso
    view.estado = out.estado
    view.puedeEscribir = out.puede_escribir
    view.motivo = out.motivo
    if (!out.sin_cambios) {
      view.rev = out.revision
      view.truncado = out.truncado
      lines.value = parseAnsiLineas(out.ansi, cacheAnsi)
    }
    view.loaded = true
    schedule(POLL_MS)
  } catch (e) {
    if (active !== paneId || mine.signal.aborted) return
    if (e instanceof ApiError && (e.status === 404 || e.status === 403)) {
      view.gone = e.status === 404 ? 'La terminal ya no está' : e.detail || 'No se puede ver esta terminal'
      stopWatching()
      return
    }
    if (e instanceof ApiError && e.status === 429) {
      schedule(Math.max(POLL_MS, (e.retryAfter ?? 2) * 1000))
      return
    }
    view.error = e instanceof ApiError && e.status !== 0 ? e.detail : 'No llego al servidor'
    schedule(Math.min(BACKOFF_MAX, BACKOFF[Math.min(failures, BACKOFF.length - 1)]))
    failures++
  }
}

function onVisibility() {
  if (!active) return
  if (visible()) {
    view.paused = false
    void poll()
  } else {
    view.paused = true
    clearTimeout(timer)
    ctrl?.abort()
  }
}

export function watchTerminal(paneId: string): () => void {
  stopWatching()
  Object.assign(view, blank(paneId))
  lines.value = []
  active = paneId
  failures = 0
  if (typeof document !== 'undefined') document.addEventListener('visibilitychange', onVisibility)
  void poll()
  return stopWatching
}

export function stopWatching() {
  active = null
  clearTimeout(timer)
  ctrl?.abort()
  ctrl = null
  if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', onVisibility)
}

// ---------- navegación ----------
let pushed = false

function writeUrl(id: string | null, mode: 'push' | 'replace') {
  const params = new URLSearchParams(location.search)
  if (id) params.set('terminal', id)
  else params.delete('terminal')
  params.delete('session')
  const query = params.toString()
  const url = location.pathname + (query ? `?${query}` : '')
  const state = id ? { orqTerminal: id } : null
  if (mode === 'push') history.pushState(state, '', url)
  else history.replaceState(state, '', url)
}

export function openTerminal(paneId: string) {
  if (openTerminalId.value === paneId) return
  openTerminalId.value = paneId
  if (desktop.value) writeUrl(paneId, 'replace')
  else {
    writeUrl(paneId, 'push')
    pushed = true
  }
}

export function closeTerminal() {
  if (!openTerminalId.value) return
  if (!desktop.value && pushed) {
    pushed = false
    history.back()
    return
  }
  openTerminalId.value = null
  writeUrl(null, 'replace')
}

const PANE_RE = /^[A-Za-z0-9][A-Za-z0-9_:.-]{0,63}$/

/** `?terminal=<pane>` (p. ej. al tocar un aviso de terminal): solo un id válido abre el visor; nunca ejecuta nada. */
export function terminalFromUrl(search: string): string | null {
  const id = new URLSearchParams(search).get('terminal')
  return id && PANE_RE.test(id) ? id : null
}

export function initTerminalNav() {
  const link = terminalFromUrl(location.search)
  if (link) {
    pushed = false
    openTerminalId.value = link
  }
  window.addEventListener('popstate', (e) => {
    pushed = false
    openTerminalId.value = typeof e.state?.orqTerminal === 'string' ? e.state.orqTerminal : null
  })
}
