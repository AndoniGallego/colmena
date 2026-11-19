import { reactive, ref } from 'vue'
import { ApiError, type DialogAnswerRequest, type DialogChoice, type DialogView, type PedidoPermiso } from '../api/types'
import { freezeSent, huellaOf, needsPin, outcomeFor, permisoBody, preguntaBody, wantsComposer, type Outcome, type PinChoice, type Seleccion } from '../lib/dialogo'
import { newId } from '../lib/reply'
import { haptic } from '../motion'
import { answerDialog, decidirPermiso, getDialog } from './app'

type Phase = 'idle' | 'sending' | 'verifying' | 'done'

interface DialogState {
  sessionId: string | null
  view: DialogView | null
  loading: boolean
  loadError: string | null
  phase: Phase
  /** What the server said when it refused or could not confirm; shown inside the card. */
  notice: string | null
  noticeKind: Outcome['kind'] | null
  pin: PinState
  /** Fingerprints that already got keys, even through a failed attempt. */
  sent: string[]
}

interface PinState {
  open: boolean
  error: string | null
  lockedUntil: number | null
  /** The prompt and rule the user was looking at when the sheet opened. */
  huella: string | null
  regla: string | null
  choice: PinChoice | null
  pedidoId: string | null
}

let trackedPedidoId: string | null = null

const closedPin = (): PinState => ({
  open: false,
  error: null,
  lockedUntil: null,
  huella: null,
  regla: null,
  choice: null,
  pedidoId: null,
})

export const dlg = reactive<DialogState>({
  sessionId: null,
  view: null,
  loading: false,
  loadError: null,
  phase: 'idle',
  notice: null,
  noticeKind: null,
  pin: closedPin(),
  sent: [],
})

/** Bumped when the composer should take focus (after "No", Claude waits for new instructions). */
export const composerRequest = ref(0)

const VERIFY_AFTER_MS = 700
const DONE_FLASH_MS = 1600
let token = 0
let verifyTimer: ReturnType<typeof setTimeout> | undefined
let doneTimer: ReturnType<typeof setTimeout> | undefined

export function resetDialog(sessionId: string | null) {
  token++
  clearTimeout(verifyTimer)
  clearTimeout(doneTimer)
  dlg.sessionId = sessionId
  dlg.view = null
  dlg.loading = false
  dlg.loadError = null
  dlg.phase = 'idle'
  dlg.notice = null
  dlg.noticeKind = null
  dlg.pin = closedPin()
  dlg.sent = []
  trackedPedidoId = null
}

function trackPedido(view: DialogView) {
  trackedPedidoId = view.tipo === 'pedido' ? view.pedido.id : null
}

export async function loadDialog(sessionId: string, opts: { keepNotice?: boolean } = {}) {
  if (dlg.sessionId !== sessionId) resetDialog(sessionId)
  if (dlg.phase === 'sending' || dlg.phase === 'verifying') return
  const mine = ++token
  dlg.loading = !dlg.view
  try {
    const view = await getDialog(sessionId)
    if (mine !== token) return
    const same = !!dlg.view && !!huellaOf(view) && huellaOf(dlg.view) === huellaOf(view)
    dlg.view = freezeSent(view, dlg.sent)
    trackPedido(dlg.view)
    dlg.loadError = null
    if (!opts.keepNotice && !same) {
      dlg.notice = null
      dlg.noticeKind = null
    }
    if (dlg.pin.open && dlg.pin.huella !== huellaOf(view)) {
      dlg.pin = closedPin()
      dlg.notice = 'El diálogo cambió'
      dlg.noticeKind = 'stale'
      haptic([30, 40, 30])
    }
  } catch (e) {
    if (mine !== token) return
    if (e instanceof ApiError && e.status === 401) return
    dlg.loadError = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  } finally {
    if (mine === token) dlg.loading = false
  }
}

function succeed(choice: DialogChoice | null, interrumpida: boolean) {
  clearTimeout(verifyTimer)
  dlg.phase = 'done'
  dlg.notice = null
  dlg.noticeKind = null
  dlg.pin.open = false
  haptic([10, 40, 16])
  if (choice && wantsComposer(choice, interrumpida)) composerRequest.value++
  clearTimeout(doneTimer)
  doneTimer = setTimeout(() => {
    if (dlg.phase === 'done') dlg.phase = 'idle'
  }, DONE_FLASH_MS)
}

async function submit(body: DialogAnswerRequest, choice: DialogChoice | null): Promise<Outcome | null> {
  if (dlg.phase !== 'idle') return null
  dlg.phase = 'sending'
  dlg.notice = null
  dlg.noticeKind = null
  verifyTimer = setTimeout(() => dlg.phase === 'sending' && (dlg.phase = 'verifying'), VERIFY_AFTER_MS)
  try {
    const r = await answerDialog(body)
    if (!r.ok) throw new ApiError(502, 'No se confirmó la respuesta: mirá la terminal')
    succeed(choice, r.interrumpida)
    return null
  } catch (e) {
    clearTimeout(verifyTimer)
    const out = outcomeFor(e)
    if (out.kind === 'done') {
      succeed(null, false)
      return out
    }
    dlg.phase = 'idle'
    if (e instanceof ApiError && e.status === 401 && out.kind !== 'pin') return out
    if (out.kind !== 'pin' && out.kind !== 'limit') {
      dlg.notice = out.message
      dlg.noticeKind = out.kind
    }
    if (out.kind === 'half') {
      dlg.sent.push(body.huella)
      if (dlg.view) dlg.view = freezeSent(dlg.view, dlg.sent)
    }
    if (out.kind === 'stale' || out.kind === 'half') {
      haptic([30, 40, 30])
      if (dlg.sessionId) void loadDialog(dlg.sessionId, { keepNotice: true })
    }
    return out
  }
}

/** `seen` is the fingerprint of the prompt the user actually looked at; the server refuses if it moved on. */
export function answerPermiso(choice: DialogChoice, pin?: string, seen?: string): Promise<Outcome | null> {
  const body = dlg.view && dlg.sessionId ? permisoBody(dlg.view, dlg.sessionId, newId(), choice, pin) : null
  if (!body) return Promise.resolve(null)
  if (seen) body.huella = seen
  return submit(body, choice)
}

export function answerPregunta(sel: Seleccion): Promise<Outcome | null> {
  const body = dlg.view && dlg.sessionId ? preguntaBody(dlg.view, dlg.sessionId, newId(), sel) : null
  if (!body) return Promise.resolve(null)
  return submit(body, null)
}

export function askPin(choice: PinChoice = 'si_siempre') {
  const v = dlg.view
  let regla: string | null = null
  let huella: string | null = huellaOf(v) || null
  let pedidoId: string | null = null
  if (v?.tipo === 'permiso') regla = v.permiso.regla
  else if (v?.tipo === 'pedido' && choice === 'siempre' && v.pedido.regla) {
    regla = v.pedido.regla.contenido
    pedidoId = v.pedido.id
    huella = v.pedido.regla.huella
  }
  dlg.pin = { ...closedPin(), open: true, choice, huella, regla, pedidoId }
}

export function closePin() {
  if (dlg.phase === 'sending' || dlg.phase === 'verifying') return
  dlg.pin = closedPin()
}

/** The PIN goes straight into the request body; it is not kept anywhere once the call returns. */
export async function confirmPin(pin: string) {
  const choice = dlg.pin.choice
  if (!pin || !choice || !needsPin(choice) || !dlg.pin.huella) return
  const out = choice === 'siempre' ? await confirmarSiempre(pin) : await answerPermiso(choice as DialogChoice, pin, dlg.pin.huella)
  if (!out) return
  if (out.kind === 'pin') dlg.pin.error = out.message
  else if (out.kind === 'limit') {
    dlg.pin.error = 'Demasiados intentos.'
    dlg.pin.lockedUntil = Date.now() + (out.retryAfter ?? 600) * 1000
  } else dlg.pin.open = false
}

function pedidoNotice(p: PedidoPermiso): string {
  if (p.estado === 'terminal') return 'Resuelto en la terminal'
  if (p.estado === 'vencido' || p.estado === 'dialogo') return 'Se contesta en el diálogo'
  if (p.estado === 'permitido') return 'Permitido'
  if (p.estado === 'rechazado') return 'Rechazado'
  if (p.estado === 'siempre') return 'Permitido siempre'
  return p.estado
}

async function decidir(
  accion: 'permitir' | 'rechazar' | 'siempre',
  extra: { motivo?: string; pin?: string; huella_regla?: string },
  pedidoId: string,
): Promise<Outcome | null> {
  if (dlg.phase !== 'idle' || dlg.view?.tipo !== 'pedido' || !dlg.sessionId) return null
  if (dlg.view.pedido.id !== pedidoId) return null
  const { pedido } = dlg.view
  dlg.phase = 'sending'
  dlg.notice = null
  dlg.noticeKind = null
  verifyTimer = setTimeout(() => dlg.phase === 'sending' && (dlg.phase = 'verifying'), VERIFY_AFTER_MS)
  const sessionAtStart = dlg.sessionId
  try {
    const next = await decidirPermiso(pedido.id, { accion, ...extra })
    clearTimeout(verifyTimer)
    if (dlg.sessionId !== sessionAtStart) {
      dlg.phase = 'idle'
      return null
    }
    dlg.view = { tipo: 'pedido', pedido: next }
    trackPedido(dlg.view)
    succeed(null, false)
    return null
  } catch (e) {
    clearTimeout(verifyTimer)
    dlg.phase = 'idle'
    const out = outcomeFor(e)
    if (e instanceof ApiError && e.status === 409) {
      await loadDialog(dlg.sessionId, { keepNotice: true })
      if (dlg.view?.tipo === 'pedido') dlg.notice = pedidoNotice(dlg.view.pedido)
      else dlg.notice = out.message
      dlg.noticeKind = 'stale'
      haptic([30, 40, 30])
      return out
    }
    if (out.kind === 'pin' || out.kind === 'limit') return out
    dlg.notice = out.message
    dlg.noticeKind = out.kind
    return out
  }
}

export function decidirPedido(id: string, accion: 'permitir' | 'rechazar', motivo?: string): Promise<Outcome | null> {
  return decidir(accion, motivo?.trim() ? { motivo: motivo.trim() } : {}, id)
}

export async function confirmarSiempre(pin: string): Promise<Outcome | null> {
  let pedidoId = dlg.pin.pedidoId
  let huellaRegla = dlg.pin.huella
  if (!pedidoId || !huellaRegla) {
    if (dlg.view?.tipo !== 'pedido' || !dlg.view.pedido.regla) return null
    pedidoId = dlg.view.pedido.id
    huellaRegla = dlg.view.pedido.regla.huella
  } else if (dlg.view?.tipo !== 'pedido' || dlg.view.pedido.id !== pedidoId) {
    dlg.pin = closedPin()
    dlg.notice = 'El diálogo cambió'
    dlg.noticeKind = 'stale'
    haptic([30, 40, 30])
    return null
  }
  return decidir('siempre', { pin, huella_regla: huellaRegla }, pedidoId)
}

/** SSE `permisos`: recarga el diálogo de la sesión abierta si le toca. */
export function onPermisosPedidos(pedidos: PedidoPermiso[]) {
  const sid = dlg.sessionId
  if (!sid || !dlg.view || dlg.phase === 'sending' || dlg.phase === 'verifying') return
  const mine = pedidos.filter((p) => p.session_id === sid)
  const tracked = trackedPedidoId ? mine.find((p) => p.id === trackedPedidoId) : undefined
  const yaNoAbierto = !!trackedPedidoId && (!tracked || (tracked.estado !== 'abierto' && tracked.estado !== 'enviando'))
  if (mine.length > 0 || yaNoAbierto) void loadDialog(sid, { keepNotice: true })
}
