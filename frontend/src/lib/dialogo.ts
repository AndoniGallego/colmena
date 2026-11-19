import {
  ApiError,
  type DialogAnswerRequest,
  type DialogChoice,
  type DialogView,
  type EstadoPedido,
  type PedidoPermiso,
  type PermisoView,
  type PreguntaItem,
  type PreguntaView,
  type ReglaPedido,
} from '../api/types'

export const MAX_OTRO = 500
export const PIN_WRONG = 'PIN incorrecto'
const CHOICES: DialogChoice[] = ['si', 'si_siempre', 'si_auto', 'si_ediciones', 'no']
const TOOLS = ['Bash', 'Write', 'Edit']

const str = (v: unknown) => (typeof v === 'string' ? v : '')
const obj = (v: unknown): Record<string, unknown> | null => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null)

const opaque = (paneId = '', pantalla = ''): DialogView => ({ tipo: 'desconocido', paneId, pantalla })

function toPermiso(raw: Record<string, unknown> | null): PermisoView | null {
  if (!raw || !TOOLS.includes(str(raw.herramienta)) || !Array.isArray(raw.opciones)) return null
  const opciones = raw.opciones.filter((o): o is DialogChoice => CHOICES.includes(o as DialogChoice))
  if (!opciones.includes('si') || !opciones.includes('no')) return null
  return {
    herramienta: raw.herramienta as PermisoView['herramienta'],
    detalle: str(raw.detalle),
    descripcion: str(raw.descripcion),
    completo: raw.completo === true,
    opciones,
    regla: typeof raw.regla === 'string' ? raw.regla : null,
    mas_en_terminal: raw.mas_en_terminal === true,
    archivo: str(raw.archivo),
    replace_all: raw.replace_all === true,
  }
}

export const MAX_PREGUNTAS = 4

function toItem(raw: unknown, alone: boolean): PreguntaItem | null {
  const q = obj(raw)
  if (!q || !Array.isArray(q.opciones) || !q.opciones.length || typeof q.multi !== 'boolean') return null
  const opciones = q.opciones.map((o) => ({ label: str(obj(o)?.label), descripcion: str(obj(o)?.descripcion) }))
  if (opciones.some((o) => !o.label)) return null
  return { header: str(q.header), texto: str(q.texto), multi: q.multi, otro: alone && !q.multi && q.otro === true, opciones }
}

const ESTADOS_PEDIDO: EstadoPedido[] = ['abierto', 'enviando', 'permitido', 'rechazado', 'siempre', 'terminal', 'vencido', 'dialogo']

function toRegla(raw: unknown): ReglaPedido | null {
  const r = obj(raw)
  if (!r || !str(r.herramienta) || !str(r.contenido) || !str(r.archivo) || !str(r.huella)) return null
  return { herramienta: str(r.herramienta), contenido: str(r.contenido), archivo: str(r.archivo), huella: str(r.huella) }
}

function toPedido(raw: Record<string, unknown> | null): PedidoPermiso | null {
  if (!raw || !str(raw.id)) return null
  const estado = str(raw.estado)
  if (!ESTADOS_PEDIDO.includes(estado as EstadoPedido)) return null
  const regla = raw.regla == null ? null : toRegla(raw.regla)
  if (raw.regla != null && !regla) return null
  const creadoRaw = raw.creado
  const creado =
    typeof creadoRaw === 'string' && creadoRaw.trim() ? creadoRaw.trim() : typeof creadoRaw === 'number' ? new Date(creadoRaw * 1000).toISOString() : null
  return {
    id: str(raw.id),
    session_id: str(raw.session_id),
    pane_id: str(raw.pane_id),
    herramienta: str(raw.herramienta),
    entrada: obj(raw.entrada) ?? {},
    estado: estado as EstadoPedido,
    creado,
    regla,
  }
}

function toPregunta(raw: Record<string, unknown> | null): PreguntaView | null {
  const list = Array.isArray(raw?.preguntas) ? raw!.preguntas : []
  if (!list.length || list.length > MAX_PREGUNTAS) return null
  const preguntas = list.map((q) => toItem(q, list.length === 1))
  return preguntas.every((q) => q) ? { preguntas: preguntas as PreguntaItem[] } : null
}

/** Anything the UI cannot show with certainty falls back to the read-only view; it never invents an answerable card. */
export function normalizeDialog(raw: unknown): DialogView {
  const d = obj(raw)
  if (!d) return opaque()
  if (d.tipo === 'ninguno') return { tipo: 'ninguno' }
  const paneId = str(d.pane_id)
  if (d.tipo === 'permiso' && str(d.huella) && paneId) {
    const permiso = toPermiso(obj(d.permiso))
    if (permiso) return { tipo: 'permiso', huella: str(d.huella), paneId, permiso }
  }
  if (d.tipo === 'pregunta' && str(d.huella) && paneId) {
    const pregunta = toPregunta(obj(d.pregunta))
    if (pregunta) return { tipo: 'pregunta', huella: str(d.huella), paneId, pregunta }
  }
  if (d.tipo === 'pedido') {
    const pedido = toPedido(obj(d.pedido))
    if (pedido) return { tipo: 'pedido', pedido }
  }
  return opaque(paneId, str(d.pantalla))
}

export const CHOICE_LABEL: Record<DialogChoice, string> = {
  si: 'Sí',
  si_siempre: 'Sí, y no volver a preguntar',
  si_auto: 'Sí y pasar a modo automático',
  si_ediciones: 'Sí y aceptar todas las ediciones',
  no: 'No',
}

/** Choices that change what the session asks from now on; they are not offered as a plain tap. */
export const isModeChoice = (c: DialogChoice) => c === 'si_auto' || c === 'si_ediciones'

export interface PinCopy {
  note: string
  code: string | null
  tail: string
  confirm: string
}

/** What the PIN sheet says before the user confirms: the consequence, in plain words. */
export function pinCopy(c: PinChoice, regla: string | null): PinCopy {
  if (c === 'si_auto')
    return { note: 'Desde ahora esta sesión deja de pedirte permiso para comandos. Claude va a poder correr lo que necesite sin preguntarte, aunque no estés mirando. Vale mientras dure la sesión; en la terminal se vuelve atrás con shift+tab.', code: null, tail: '', confirm: 'Confirmar y pasar a modo automático' }
  if (c === 'si_ediciones')
    return { note: 'Desde ahora esta sesión deja de pedirte permiso para ediciones. Claude va a poder crear y modificar archivos sin preguntarte, aunque no estés mirando. Vale mientras dure la sesión; en la terminal se vuelve atrás con shift+tab.', code: null, tail: '', confirm: 'Confirmar y aceptar las ediciones' }
  return {
    note: `“Sí, y no volver a preguntar” guarda una regla permanente${regla ? ':' : '.'}`,
    code: regla,
    tail: 'Claude va a poder repetirlo sin pedirte permiso, aunque no estés mirando.',
    confirm: 'Confirmar y permitir siempre',
  }
}

export function toolTitle(p: PermisoView): string {
  if (p.herramienta === 'Bash') return 'Quiere correr un comando'
  return p.herramienta === 'Write' ? 'Quiere crear un archivo' : 'Quiere editar un archivo'
}

/** Every choice that outlives this prompt (a saved rule or a mode switch) asks for the PIN first. */
export type PinChoice = DialogChoice | 'siempre'

export const needsPin = (c: PinChoice) => c !== 'si' && c !== 'no'

/** The command or diff the server flagged as cut short must be reviewed in the terminal before saying yes. */
export const canApprove = (p: PermisoView, c: DialogChoice) => p.opciones.includes(c) && (c === 'no' || p.completo)

export const huellaOf = (v: DialogView | null): string => {
  if (!v) return ''
  if ('huella' in v && v.huella) return v.huella
  if (v.tipo === 'pedido') return v.pedido.regla?.huella ?? v.pedido.id
  return ''
}

/** The card swapped to a different prompt under the user's finger. */
export const dialogChanged = (prev: string, next: string) => !!prev && !!next && prev !== next

/** A prompt that already received keys (even if the attempt failed) is never offered again from the app. */
export function freezeSent(v: DialogView, sent: string[]): DialogView {
  const h = huellaOf(v)
  return h && sent.includes(h) && 'paneId' in v ? { tipo: 'desconocido', paneId: v.paneId, pantalla: '' } : v
}

export function permisoBody(v: DialogView, sessionId: string, id: string, choice: DialogChoice, pin?: string): DialogAnswerRequest | null {
  if (v.tipo !== 'permiso' || !canApprove(v.permiso, choice)) return null
  const body: DialogAnswerRequest = { id, session_id: sessionId, pane_id: v.paneId, huella: v.huella, tipo: 'permiso', permiso: choice }
  if (needsPin(choice)) {
    if (!pin) return null
    body.pin = pin
  }
  return body
}

export function otroProblem(text: string): string | null {
  const t = text.trim()
  if (!t) return 'Escribí la respuesta'
  // eslint-disable-next-line no-control-regex
  if (/[\x00-\x1f\x7f-\x9f\u2028\u2029]/.test(t)) return 'No puede tener saltos de línea ni caracteres de control'
  return t.length > MAX_OTRO ? `Máximo ${MAX_OTRO} caracteres (van ${t.length})` : null
}

/** `opciones[i]` holds the picked option indexes of question i. */
export type Seleccion = { opciones: number[][] } | { otro: string } | null

/** A simple question needs exactly one pick, a multi one at least one; never repeated or out of range. */
export function seleccionComplete(p: PreguntaView, opciones: number[][]): boolean {
  return opciones.length === p.preguntas.length && p.preguntas.every((q, i) => answered(q, opciones[i]))
}

export function answered(q: PreguntaItem, picks: number[] | undefined): boolean {
  if (!picks || !picks.length || new Set(picks).size !== picks.length) return false
  if (!q.multi && picks.length !== 1) return false
  return picks.every((n) => Number.isInteger(n) && n >= 0 && n < q.opciones.length)
}

const MAX_PICKS = 6

export function preguntaBody(v: DialogView, sessionId: string, id: string, sel: Seleccion): DialogAnswerRequest | null {
  if (v.tipo !== 'pregunta' || !sel) return null
  const base = { id, session_id: sessionId, pane_id: v.paneId, huella: v.huella, tipo: 'pregunta' as const }
  const qs = v.pregunta.preguntas
  if ('otro' in sel) return qs.length === 1 && qs[0].otro && !otroProblem(sel.otro) ? { ...base, respuestas: [{ otro: sel.otro.trim() }] } : null
  if (!seleccionComplete(v.pregunta, sel.opciones) || sel.opciones.some((p) => p.length > MAX_PICKS)) return null
  return { ...base, respuestas: sel.opciones.map((p) => ({ opciones: [...p].sort((a, b) => a - b) })) }
}

export type Outcome =
  | { kind: 'done'; message: string }
  | { kind: 'stale'; message: string }
  | { kind: 'half'; message: string }
  | { kind: 'pin'; message: string }
  | { kind: 'limit'; message: string; retryAfter: number | null }
  | { kind: 'error'; message: string }

/** Maps the server's answer to what the card does next; an unknown failure never reads as success. */
export function outcomeFor(e: unknown): Outcome {
  if (!(e instanceof ApiError)) return { kind: 'error', message: 'Se cortó la conexión: mirá la terminal antes de reintentar' }
  if (e.status === 409 && /ya se respondió/i.test(e.detail)) return { kind: 'done', message: 'Ya estaba respondido' }
  if (e.status === 409 && /ya se mandó/i.test(e.detail)) return { kind: 'half', message: e.detail }
  if (e.status === 409) return { kind: 'stale', message: e.detail }
  if (e.status === 502) return { kind: 'half', message: e.detail }
  if (e.status === 401 && e.detail === PIN_WRONG) return { kind: 'pin', message: PIN_WRONG }
  if (e.status === 429) return { kind: 'limit', message: e.detail, retryAfter: e.retryAfter }
  return { kind: 'error', message: e.detail }
}

/** After "No" Claude Code stops and waits for new instructions, so the composer takes focus. */
export const wantsComposer = (choice: DialogChoice, interrumpida: boolean) => interrumpida || choice === 'no'

/** Plain text only: the screen comes from the terminal and is shown as-is, trimmed of blank edges. */
export function screenText(pantalla: string, maxLines = 30): string {
  const lines = pantalla.replace(/\r/g, '').split('\n')
  while (lines.length && !lines[lines.length - 1].trim()) lines.pop()
  while (lines.length && !lines[0].trim()) lines.shift()
  return lines.slice(-maxLines).join('\n')
}
