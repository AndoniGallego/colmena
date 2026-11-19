import type { DiosDia, DiosTokens } from '../api/types'

export function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(n >= 10_000_000 ? 0 : 1).replace(/\.0$/, '')} M`
  if (n >= 10_000) return `${Math.round(n / 1000)} k`
  if (n >= 1000) return `${(n / 1000).toFixed(1).replace(/\.0$/, '')} k`
  return String(Math.round(n))
}

export type DesgloseKey = 'input' | 'cache_write' | 'cache_read' | 'output'
export const DESGLOSE: { key: DesgloseKey; label: string }[] = [
  { key: 'input', label: 'Entrada' },
  { key: 'cache_write', label: 'Escrito en caché' },
  { key: 'cache_read', label: 'Leído de caché' },
  { key: 'output', label: 'Salida' },
]

export interface Tramo {
  key: DesgloseKey
  label: string
  n: number
  pct: number
}

export function desglose(t: Pick<DiosTokens, DesgloseKey>): Tramo[] {
  const total = t.input + t.cache_write + t.cache_read + t.output
  return DESGLOSE.map(({ key, label }) => ({ key, label, n: t[key], pct: total ? (t[key] * 100) / total : 0 }))
}

export interface Barra {
  fecha: string
  total: number
  /** Altura 0..1 contra el día más alto (o el tope, si es mayor). */
  h: number
  tope: boolean
  label: string
}

const DIAS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
export function diaLabel(fecha: string): string {
  const [y, m, d] = fecha.split('-').map(Number)
  if (!y || !m || !d) return fecha
  return `${DIAS[new Date(y, m - 1, d).getDay()]} ${d}`
}

export function barras(dias: DiosDia[], n: number, tope: number): { barras: Barra[]; topeH: number | null } {
  const rows = dias.slice(-n)
  const max = Math.max(1, tope, ...rows.map((d) => d.total))
  return {
    barras: rows.map((d) => ({ fecha: d.fecha, total: d.total, h: d.total / max, tope: tope > 0 && d.total >= tope, label: diaLabel(d.fecha) })),
    topeH: tope > 0 ? tope / max : null,
  }
}
