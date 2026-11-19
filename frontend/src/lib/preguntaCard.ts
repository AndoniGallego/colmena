import { quitarRefNovedad } from './novedadesFilas'
export interface PreguntaRef {
  sig: string
  recomendada?: string
  porque?: string
}

const clip = (v: unknown, max: number) => {
  const t = typeof v === 'string' ? v.trim() : ''
  return t.length > max ? `${t.slice(0, max - 1).trimEnd()}…` : t
}

export function toPreguntaRef(value: unknown): PreguntaRef | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  const sig = clip(o.sig, 120)
  if (!sig) return null
  const out: PreguntaRef = { sig }
  const rec = clip(o.recomendada, 80)
  if (rec) out.recomendada = rec
  const pq = clip(o.porque, 200)
  if (pq) out.porque = pq
  return out
}

export function indiceUltimaPorSig(rows: { idx: number; sigs: string[] }[]): Map<string, number> {
  const out = new Map<string, number>()
  for (const r of rows) for (const sig of r.sigs) out.set(sig, r.idx)
  return out
}

export type EstadoTarjeta = 'activa' | 'obsoleta' | 'sin_lote' | 'contestada'

export function estadoTarjeta(p: { hayLote: boolean; esUltima: boolean; contestada: string | null }): EstadoTarjeta {
  if (p.contestada) return 'contestada'
  if (!p.hayLote) return 'sin_lote'
  if (!p.esUltima) return 'obsoleta'
  return 'activa'
}

type LoteLite = { preguntas: { opciones: { label: string; recomendada: boolean }[] }[] }

export function recomendadaLabel(bloque: PreguntaRef, lote: LoteLite | null | undefined): string | null {
  if (bloque.recomendada) return bloque.recomendada
  if (!lote) return null
  for (const q of lote.preguntas) {
    const o = q.opciones.find((x) => x.recomendada)
    if (o) return o.label
  }
  return null
}

const PANE_ID = /\([a-zA-Z0-9_-]+:[a-zA-Z0-9_-]+\)\s*/g
const SIG = /\s*\(sig=[^)]+\)/g
const PEDIDO = /\s*\(pedido_id=[^)]+\)/g

/** Lo que se muestra en la tarjeta plegada de novedades (Centinela sigue viendo el texto crudo). */
export function limpiarFilaNovedad(fila: string): string {
  return quitarRefNovedad(fila)
    .replace(SIG, '')
    .replace(PEDIDO, '')
    .replace(PANE_ID, ' ')
    .replace(/\s{2,}/g, ' ')
    .trim()
}
