/** Cierre de un mensaje de Claude: qué hizo, qué falta y qué le pide al usuario. Todo texto plano. */
export interface Estado {
  hizo?: string
  falta?: string
  pide?: string
}

export interface LineaEstado {
  clave: keyof Estado
  marca: string
  texto: string
}

export const ESTADO_CHARS = 120
const CAMPOS = ['hizo', 'falta', 'pide'] as const

export function clipPalabras(src: string, limit: number): string {
  const t = src.replace(/\s+/g, ' ').trim()
  if (t.length <= limit) return t
  const cut = t.slice(0, limit)
  const space = cut.lastIndexOf(' ')
  return `${(space > limit * 0.6 ? cut.slice(0, space) : cut).replace(/[ ,.;:]+$/, '')}…`
}

export function toEstado(value: unknown): Estado | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const out: Estado = {}
  for (const campo of CAMPOS) {
    const v = o[campo]
    if (typeof v === 'string' && v.trim()) out[campo] = clipPalabras(v, ESTADO_CHARS)
  }
  return Object.keys(out).length ? out : null
}

/** Las líneas que se muestran, en orden fijo: ✓ hizo, … falta, ? pide. */
export function lineasEstado(estado: Estado): LineaEstado[] {
  const out: LineaEstado[] = []
  if (estado.hizo) out.push({ clave: 'hizo', marca: '✓', texto: estado.hizo })
  if (estado.falta) out.push({ clave: 'falta', marca: '…', texto: `Falta: ${estado.falta}` })
  if (estado.pide) out.push({ clave: 'pide', marca: '?', texto: estado.pide })
  return out
}
