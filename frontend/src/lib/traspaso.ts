import { parseFenced } from './fence'

export type DestinoTipo = 'existente' | 'tab_nuevo' | 'workspace_nuevo'

export interface Traspaso {
  origen: string
  destino_tipo: DestinoTipo | null
  destino: string
  por_que: string
  brief_path: string
  resumen_brief: string
  pane_id: string
  workspace_id: string
  label: string
  cwd: string
  agent_name: string
}

export interface ParsedMessage {
  before: string
  after: string
  traspaso: Traspaso | null
  /** an opening ```traspaso fence was seen but not closed yet (only while streaming) */
  pending: boolean
}

const TIPOS: Record<string, DestinoTipo> = {
  existente: 'existente',
  sesion_existente: 'existente',
  tab_nuevo: 'tab_nuevo',
  tab: 'tab_nuevo',
  workspace_nuevo: 'workspace_nuevo',
  workspace: 'workspace_nuevo',
}

function normTipo(v: unknown): DestinoTipo | null {
  if (typeof v !== 'string') return null
  const k = v
    .trim()
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[\s-]+/g, '_')
  return TIPOS[k] ?? null
}

const s = (v: unknown) => (typeof v === 'string' ? v.trim() : v == null ? '' : String(v))
const lista = (v: unknown) => (Array.isArray(v) ? v.map(s).filter(Boolean).join(', ') : s(v))

export function toTraspaso(value: unknown): Traspaso | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const t: Traspaso = {
    origen: lista(o.origen),
    destino_tipo: normTipo(o.destino_tipo),
    destino: s(o.destino),
    por_que: s(o.por_que ?? o.porque),
    brief_path: s(o.brief_path),
    resumen_brief: s(o.resumen_brief),
    pane_id: s(o.pane_id),
    workspace_id: s(o.workspace_id),
    label: s(o.label),
    cwd: s(o.cwd),
    agent_name: s(o.agent_name),
  }
  return t.origen || t.destino ? t : null
}

export interface Sesion {
  name: string
  pane: string
}

/** "Nombre (wC:p1)" → nombre e id; sin paréntesis final queda todo como nombre. */
export function splitPane(v: string): Sesion {
  const m = /^(.*?)\s*\(([^()]+)\)\s*$/.exec(v.trim())
  return m && m[1] ? { name: m[1], pane: m[2] } : { name: v.trim(), pane: '' }
}

/** Separa un origen con varias sesiones ("A (wC:p1), B (wD:p1) y C") sin cortar dentro de paréntesis. */
export function parseOrigenes(origen: string): Sesion[] {
  const parts: string[] = []
  let depth = 0
  let cur = ''
  for (const ch of origen) {
    if (ch === '(') depth++
    else if (ch === ')') depth = Math.max(0, depth - 1)
    if (depth === 0 && (ch === ',' || ch === ';')) {
      parts.push(cur)
      cur = ''
    } else cur += ch
  }
  parts.push(cur)
  return parts
    .flatMap((p) => p.split(/(?<=\))\s+y\s+/))
    .map((p) => p.trim().replace(/^y\s+/, ''))
    .filter(Boolean)
    .map(splitPane)
}

const REQUIRED: Record<DestinoTipo, (keyof Traspaso)[]> = {
  existente: ['pane_id'],
  tab_nuevo: ['workspace_id', 'label', 'cwd', 'agent_name'],
  workspace_nuevo: ['label', 'cwd', 'agent_name'],
}

/** Fields the server needs to execute the handoff that the proposal does not carry. */
export function missingExecFields(t: Traspaso): string[] {
  if (!t.destino_tipo) return ['destino_tipo']
  const missing = ['brief_path', ...REQUIRED[t.destino_tipo]].filter((k) => !t[k as keyof Traspaso])
  return missing
}

export const isExecutable = (t: Traspaso) => missingExecFields(t).length === 0

const HANDOFF_NAME = /^[a-z0-9][a-z0-9-]{0,80}\.md$/

/** Basename of brief_path when it can be requested from /api/handoffs, else null. */
export function handoffName(briefPath: string): string | null {
  const name = briefPath.split('/').pop() ?? ''
  return HANDOFF_NAME.test(name) ? name : null
}

export function parseTraspaso(text: string, streaming = false): ParsedMessage {
  const { before, after, value, pending } = parseFenced(text, 'traspaso', toTraspaso, streaming)
  return { before, after, traspaso: value, pending }
}

/** JSON for /api/traspaso/execute: the parsed block without empty fields. */
export function execBody(t: Traspaso): Record<string, string> | null {
  if (!isExecutable(t)) return null
  return Object.fromEntries(Object.entries(t).filter(([, v]) => v)) as Record<string, string>
}

/** Cuerpo para armar sin Centinela la variante tab/workspace nuevo; null si el cambio necesita razonar. */
export function variantBody(t: Traspaso, choice: TraspasoChoice): Record<string, string> | null {
  if ((choice !== 'tab_nuevo' && choice !== 'workspace_nuevo') || !t.brief_path) return null
  return Object.fromEntries(Object.entries({ ...t, destino_tipo: choice }).filter(([, v]) => v)) as Record<string, string>
}

export type TraspasoChoice = 'mandar' | DestinoTipo | 'editar'

export const CHOICE_TEXT: Record<Exclude<TraspasoChoice, 'editar'>, string> = {
  mandar: 'sí, mandalo',
  existente: 'mejor a sesión existente',
  tab_nuevo: 'mejor a tab nuevo',
  workspace_nuevo: 'mejor a workspace nuevo',
}

export const EDIT_PREFIX = 'Cambiá el brief: '
