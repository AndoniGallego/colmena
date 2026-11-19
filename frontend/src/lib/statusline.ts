import type { AgentCtx, StatusLine } from '../api/types'
import { ctxShort } from './contexto'

export interface StatusParts {
  model: string
  ctx: { text: string } | null
  vpn: 'up' | 'down' | null
}

/** El contexto va en tono neutro: `ctx_level` llega por compatibilidad pero no se usa. */
export function statusParts(sl: StatusLine | null, ctx?: AgentCtx | null): StatusParts | null {
  if (!sl) return null
  const text = ctx ? ctxShort(ctx) : sl.ctx_pct === null ? '' : `${sl.ctx_pct}%`
  return { model: sl.model, ctx: text ? { text } : null, vpn: sl.vpn }
}

/** Plain-text form, in the order Modelo · CTX · VPN. */
export function statusText(p: StatusParts): string {
  return [p.model, p.ctx?.text, p.vpn ? 'VPN ●' : ''].filter(Boolean).join(' · ')
}
