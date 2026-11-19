import type { AgentCtx, CtxCompact } from '../api/types'
import { ago } from './time'

/** 999 -> "999", 179402 -> "179k", 1000000 -> "1M", 1500000 -> "1,5M". */
export function fmtTokens(n: number): string {
  if (n < 1000) return String(n)
  if (n < 1_000_000) return `${Math.round(n / 1000)}k`
  const m = Math.round(n / 100_000) / 10
  return `${String(m).replace('.', ',')}M`
}

export const ctxLabel = (c: AgentCtx) => `${c.pct}%`

/** Texto corto del chat de sesión: "18% · 179k". */
export const ctxShort = (c: AgentCtx) => `${c.pct}% · ${fmtTokens(c.tokens)}`

export function compactText(c: Pick<CtxCompact, 'pre' | 'post'>): string {
  return `${fmtTokens(c.pre)} → ${fmtTokens(c.post)}`
}

/** "179k de 1M tokens · compactada 2 veces, la última hace 3 h (229k → 23k)". */
export function ctxLine(c: AgentCtx, now: number): string {
  const base = `${fmtTokens(c.tokens)} de ${fmtTokens(c.window)} tokens`
  if (!c.compactaciones) return base
  const veces = c.compactaciones === 1 ? 'compactada 1 vez' : `compactada ${c.compactaciones} veces`
  const last = c.ultima_compactacion
  const cuando = last ? ago(last.ts, now) : ''
  const tail = last ? ` (${compactText(last)})` : ''
  return `${base} · ${veces}${cuando ? `, la última ${cuando}` : ''}${tail}`
}

/** Fracción 0-1 del anillo; la escala es la ventana entera. */
export const ringFraction = (c: AgentCtx | null | undefined) => (c ? Math.max(0, Math.min(1, c.pct / 100)) : 0)
