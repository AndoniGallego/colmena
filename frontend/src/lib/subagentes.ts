import type { Subagente } from '../api/types'

export const VISIBLE_MAX = 5

export function elapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  if (s < 60) return `${s} s`
  const m = Math.floor(s / 60)
  if (m < 60) return `${m} min`
  const h = Math.floor(m / 60)
  return m % 60 ? `${h} h ${m % 60} min` : `${h} h`
}

export function heading(items: Subagente[]): string {
  const n = items.filter((a) => a.estado === 'trabajando').length
  const one = (k: number) => (k === 1 ? '1 agente' : `${k} agentes`)
  if (n) return `${one(n)} trabajando`
  if (items.every((a) => a.estado === 'termino')) return `${one(items.length)} ${items.length === 1 ? 'terminó' : 'terminaron'}`
  return `${one(items.length)} sin actividad`
}

/** El que arrancó último entre los que trabajan; si nadie trabaja, el primero de la lista. */
export function latest(items: Subagente[]): Subagente | null {
  const w = items.filter((a) => a.estado === 'trabajando')
  if (!w.length) return items[0] ?? null
  return w.reduce((a, b) => (b.segundos < a.segundos ? b : a))
}

export function stepOf(a: Subagente): string {
  return a.estado === 'sin_actividad' ? 'Sin actividad hace un rato' : a.paso
}

export function shown(items: Subagente[], all: boolean): Subagente[] {
  return all ? items : items.slice(0, VISIBLE_MAX)
}

export function anyWorking(items: Subagente[]): boolean {
  return items.some((a) => a.estado === 'trabajando')
}
