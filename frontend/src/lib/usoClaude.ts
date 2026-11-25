import type { DiosDia, DiosTokens } from '../api/types'
import { fmtTokens } from './tokens'

export type UsoRango = 'hoy' | '7d' | '30d'
export type UsoAgrupar = 'sesiones' | 'proyectos' | 'modelos'
export type FilaTipo = '' | 'otras'

/** Costo equivalente en la API: null si ningún modelo del grupo tiene precio; parcial si falta el de alguno. */
export interface UsoCosto {
  usd: number | null
  usdParcial: boolean
}

export type UsoTotal = DiosTokens & UsoCosto
export type UsoDia = DiosDia & UsoCosto

export interface UsoHoy {
  total: number
  usd: number | null
}

export interface UsoFila extends DiosTokens, UsoCosto {
  id: string
  nombre: string
  detalle: string
  tipo: FilaTipo
}

export interface UsoLimite {
  pct: number
  resetsAt: string | null
  vencido: boolean
}

export interface UsoLimites {
  fiveHour: UsoLimite | null
  sevenDay: UsoLimite | null
  actualizado: string | null
}

export interface ClaudeUso {
  generado: string
  totales: Record<UsoRango, UsoTotal>
  historial: UsoDia[]
  desglose: Record<UsoRango, Record<UsoAgrupar, UsoFila[]>>
  limites: UsoLimites | null
}

export const RANGOS: UsoRango[] = ['hoy', '7d', '30d']
export const AGRUPAR: UsoAgrupar[] = ['sesiones', 'proyectos', 'modelos']
export const RANGO_LABEL: Record<UsoRango, string> = { hoy: 'Hoy', '7d': '7 días', '30d': '30 días' }
export const AGRUPAR_LABEL: Record<UsoAgrupar, string> = { sesiones: 'Sesiones', proyectos: 'Proyectos', modelos: 'Modelos' }

const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0)
const s = (v: unknown) => (typeof v === 'string' ? v : '')

function tokens(raw: any): DiosTokens {
  return { input: n(raw?.input), cache_write: n(raw?.cache_write), cache_read: n(raw?.cache_read), output: n(raw?.output), mensajes: n(raw?.mensajes), total: n(raw?.total) }
}

const usdOf = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : null)

function costo(raw: any): UsoCosto {
  return { usd: usdOf(raw?.usd), usdParcial: raw?.usd_parcial === true }
}

function fila(raw: any): UsoFila | null {
  if (!raw || typeof raw.id !== 'string' || !raw.id) return null
  const tipo: FilaTipo = raw.tipo ? 'otras' : ''
  return { id: raw.id, nombre: s(raw.nombre) || raw.id, detalle: s(raw.detalle), tipo, ...tokens(raw), ...costo(raw) }
}

function limite(raw: any): UsoLimite | null {
  if (!raw || typeof raw.pct !== 'number' || !Number.isFinite(raw.pct)) return null
  const resetsAt = typeof raw.resets_at === 'string' && !Number.isNaN(Date.parse(raw.resets_at)) ? raw.resets_at : null
  return { pct: Math.max(0, Math.min(100, raw.pct)), resetsAt, vencido: raw.vencido === true }
}

export function normalizeClaudeUso(raw: any): ClaudeUso {
  const totales = {} as Record<UsoRango, UsoTotal>
  const desglose = {} as Record<UsoRango, Record<UsoAgrupar, UsoFila[]>>
  for (const r of RANGOS) {
    totales[r] = { ...tokens(raw?.totales?.[r]), ...costo(raw?.totales?.[r]) }
    desglose[r] = {} as Record<UsoAgrupar, UsoFila[]>
    for (const a of AGRUPAR) {
      const list = raw?.desglose?.[r]?.[a]
      desglose[r][a] = (Array.isArray(list) ? list : []).map(fila).filter((f: UsoFila | null): f is UsoFila => f !== null)
    }
  }
  const historial = (Array.isArray(raw?.historial) ? raw.historial : [])
    .filter((d: any) => typeof d?.fecha === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(d.fecha))
    .map((d: any) => ({ fecha: d.fecha as string, ...tokens(d), ...costo(d) }))
  const l = raw?.limites
  const fiveHour = limite(l?.five_hour)
  const sevenDay = limite(l?.seven_day)
  const limites = fiveHour || sevenDay ? { fiveHour, sevenDay, actualizado: s(l?.actualizado) || null } : null
  return { generado: s(raw?.generado), totales, historial, desglose, limites }
}

const PALETA = ['var(--st-working)', '#a78bfa', 'var(--st-blocked)', 'var(--st-done)', '#f472b6', '#22d3ee', '#a3e635', '#fb923c']

export interface DesgloseItem {
  key: string
  label: string
  sub: string
  n: number
  pct: number
  color: string
  tipo: FilaTipo
  tokens: DiosTokens
  usd?: number | null
  usdParcial?: boolean
}

/** Filas del desglose listas para la barra: porcentaje sobre el total y un color estable por posición. */
export function itemsDesglose(filas: UsoFila[]): DesgloseItem[] {
  const total = filas.reduce((acc, f) => acc + f.total, 0)
  let i = 0
  return filas.map((f) => {
    const color = f.tipo === 'otras' ? 'var(--text-4)' : PALETA[i++ % PALETA.length]
    const { id, nombre, detalle, tipo, usd, usdParcial, ...tk } = f
    return { key: id, label: nombre, sub: detalle, n: f.total, pct: total ? (f.total * 100) / total : 0, color, tipo, tokens: tk, usd, usdParcial }
  })
}

export function pctLabel(pct: number, n: number): string {
  return pct < 1 && n > 0 ? '<1' : String(Math.round(pct))
}

const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']

/** «se reinicia en 2 h 10 min» o «se reinicia el lun 3 a las 14:00». */
export function reinicioLabel(lim: UsoLimite, now: Date = new Date()): string {
  if (lim.vencido) return 'ya se reinició'
  if (!lim.resetsAt) return 'sin hora de reinicio'
  const at = new Date(lim.resetsAt)
  const min = Math.round((at.getTime() - now.getTime()) / 60_000)
  if (min <= 0) return 'ya se reinició'
  if (min < 60) return `se reinicia en ${min} min`
  if (min < 24 * 60) {
    const h = Math.floor(min / 60)
    const m = min % 60
    return `se reinicia en ${h} h${m ? ` ${m} min` : ''}`
  }
  const hh = String(at.getHours()).padStart(2, '0')
  const mm = String(at.getMinutes()).padStart(2, '0')
  return `se reinicia el ${DIAS[at.getDay()]} ${at.getDate()} a las ${hh}:${mm}`
}

export type LimiteEstado = 'ok' | 'aviso' | 'tope'
export const limiteEstado = (pct: number): LimiteEstado => (pct >= 95 ? 'tope' : pct >= 75 ? 'aviso' : 'ok')

/** Una línea con el detalle por tipo de token, para el hover y la vista expandida. */
export function detalleTokens(t: DiosTokens): string {
  const cache = t.cache_read + t.cache_write
  return `${fmtTokens(t.input)} entrada · ${fmtTokens(cache)} caché · ${fmtTokens(t.output)} salida · ${t.mensajes} ${t.mensajes === 1 ? 'mensaje' : 'mensajes'}`
}

const USD = new Intl.NumberFormat('es-AR', { style: 'currency', currency: 'USD' })

/** Dólares equivalentes en la API; «—» si el modelo no tiene precio (nunca $0). */
export function fmtUsd(usd: number | null | undefined): string {
  return usd === null || usd === undefined ? '—' : USD.format(usd)
}

/** «312 k tok · ≈ US$ 4,10 hoy» para la tarjeta de la sesión; vacío si hoy no usó nada. */
export function usoHoyLine(uso: UsoHoy | null | undefined): string {
  if (!uso || uso.total <= 0) return ''
  return `${fmtTokens(uso.total)} tok · ≈ ${fmtUsd(uso.usd)} hoy`
}
