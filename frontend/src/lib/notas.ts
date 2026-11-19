import type { Nota } from '../api/types'

export type FiltroNotas = 'todas' | 'para-hacer' | 'apuntes' | 'hechas'

const pendiente = (n: Nota) => n.tipo === 'recordatorio' && !n.hecha_at

export function filtrarNotas(l: Nota[], f: FiltroNotas): Nota[] {
  if (f === 'para-hacer') return l.filter(pendiente)
  if (f === 'hechas') return l.filter((n) => n.tipo === 'recordatorio' && !!n.hecha_at)
  if (f === 'apuntes') return l.filter((n) => n.tipo === 'apunte')
  return l
}

export const contarPendientes = (l: Nota[]): number => l.filter(pendiente).length

export const TOPE_NOTAS_NOTCH = 4

/** Notas del notch: las no hechas, más nuevas primero (el componente muestra hasta TOPE_NOTAS_NOTCH). */
export function notasNotch(l: Nota[]): Nota[] {
  return l.filter((n) => !n.hecha_at).sort((a, b) => b.creada_at.localeCompare(a.creada_at))
}

export function notaDeMensaje(l: Nota[], sid: string, ts: string): Nota | undefined {
  if (!ts) return undefined
  return l.find((n) => n.origen?.sid === sid && n.origen.ts === ts)
}

export const TOPE_NOTA = 4000

/** Recorta al tope del servidor dejando el "…" dentro del límite. */
export function recortarNota(texto: string, tope = TOPE_NOTA): { texto: string; recortado: boolean } {
  const cp = [...texto]
  if (cp.length <= tope) return { texto, recortado: false }
  return { texto: cp.slice(0, tope - 1).join('') + '…', recortado: true }
}

/** Para etiquetas de accesibilidad: el texto de una nota puede tener miles de caracteres. */
export function corto(texto: string, max = 140): string {
  const cp = [...texto]
  return cp.length <= max ? texto : cp.slice(0, max - 1).join('').trimEnd() + '…'
}
