import type { CloseBlocker, ClosePane, ClosePreview, CloseRequest, CloseSession, CloseTipo, Tab, Workspace } from '../api/types'
import { parseFenced } from './fence'

export interface Cerrar {
  id: string
  tipo: CloseTipo
  target_id: string
  destino: string
  por_que: string
}

export interface ParsedCerrar {
  before: string
  after: string
  cerrar: Cerrar | null
  /** an opening ```cerrar fence was seen but not closed yet (only while streaming) */
  pending: boolean
}

const ID = /^[A-Za-z0-9_-]{8,64}$/
const TARGET = /^[A-Za-z0-9][A-Za-z0-9_:.-]*$/
const SESSION = /^[A-Za-z0-9_-]{8,64}$/
const s = (v: unknown) => (typeof v === 'string' ? v.trim() : v == null ? '' : String(v))

export function toCerrar(value: unknown): Cerrar | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const tipo = s(o.tipo).toLowerCase()
  const c: Cerrar = {
    id: s(o.id),
    tipo: tipo === 'workspace' ? 'workspace' : tipo === 'tab' ? 'tab' : ('' as CloseTipo),
    target_id: s(o.target_id),
    destino: s(o.destino),
    por_que: s(o.por_que ?? o.porque),
  }
  return c.destino || c.target_id || c.tipo ? c : null
}

export function missingFields(c: Cerrar): string[] {
  return [!ID.test(c.id) && 'id', !c.tipo && 'tipo', !TARGET.test(c.target_id) && 'target_id'].filter(Boolean) as string[]
}

export function parseCerrar(text: string, streaming = false): ParsedCerrar {
  const { before, after, value, pending } = parseFenced(text, 'cerrar', toCerrar, streaming)
  return { before, after, cerrar: value, pending }
}

export const closeBody = (r: { id: string; tipo: CloseTipo; targetId: string; huella: string; origen: 'manual' | 'jefe'; destino: string; porQue: string; sinGuardar?: boolean; forzar?: boolean }): CloseRequest => ({
  id: r.id,
  tipo: r.tipo,
  target_id: r.targetId,
  huella: r.huella,
  origen: r.origen,
  destino: r.destino,
  por_que: r.porQue,
  ...(r.sinGuardar ? { sin_guardar: true } : {}),
  ...(r.forzar ? { forzar: true } : {}),
})

const NOUN: Record<CloseTipo, string> = { tab: 'tab', workspace: 'workspace' }
export const noun = (t: CloseTipo) => NOUN[t]

/** Row text for the confirmation list: "Claude · Arreglando el login", "Terminal · node". */
export function paneLine(p: ClosePane): { who: string; what: string } {
  if (p.kind) return { who: p.kind === 'claude' ? 'Claude' : p.kind, what: p.titulo || 'Sin título' }
  return { who: 'Terminal', what: p.proceso ?? '' }
}

const quote = (v: string) => `'${v.replace(/'/g, `'\\''`)}'`

// eslint-disable-next-line no-control-regex
const ODD_CHARS = /[\x00-\x1f\x7f-\x9f\u2028\u2029\u200e\u200f\u202a-\u202e\u2066-\u2069]/

/** The folder cannot be pasted into a shell safely, so the UI asks to resume by hand. */
export const unsafeCwd = (s: CloseSession) => ODD_CHARS.test(s.cwd)

/** Shell command to resume a closed Claude session; null when the ids or the folder are not safe to paste. */
export function resumeCommand(s: CloseSession): string | null {
  if (!s.session_id || !SESSION.test(s.session_id) || unsafeCwd(s)) return null
  return `${s.cwd ? `cd -- ${quote(s.cwd)} && ` : ''}claude --resume ${s.session_id}`
}

/** What the server says is about to close, by its own names and id; never what Centinela called it. */
export function targetLine(p: ClosePreview): string {
  const name = p.label || p.target_id
  if (p.tipo === 'workspace') return `Workspace ${name} (${p.target_id})`
  return `Workspace ${p.workspace_label || 'sin nombre'} · tab ${name} (${p.target_id})`
}

/** True when every blocker is "no sé si está trabajando": the only kind the user may override with "Cerrar igual". */
export const soloUnknown = (bs: CloseBlocker[]): boolean => bs.length > 0 && bs.every((b) => b.status === 'unknown')

/** Sessions that are blocking, with the reason the UI should give for each. */
export function blockerHint(status: string): string {
  if (status === 'working') return 'Está trabajando'
  if (status === 'fondo') return 'Tiene trabajo en segundo plano'
  if (status === 'blocked') return 'Espera una respuesta tuya en la terminal'
  return 'No sé si está trabajando: revisala en la terminal'
}

/**
 * In a protected workspace only a tab without Claude (marked by Herdr or seen by process) can close, and never
 * the last one (it would take the workspace with it). Just whether to offer the button: the server decides.
 */
export function protectedTabClosable(ws: Workspace, tab: Tab): boolean {
  if (!ws.pinned || ws.tabs.length < 2 || tab.agents.length) return false
  const terms = tab.terminales ?? []
  return terms.length > 0 && !terms.some((t) => t.proceso === 'claude')
}
