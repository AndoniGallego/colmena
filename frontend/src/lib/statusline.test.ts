import { describe, expect, it } from 'vitest'
import { normalizeStatusLine } from '../api/normalize'
import { statusParts, statusText } from './statusline'

const sl = { model: 'Opus 5.5', ticket: 'ABC-123 - Contador carrito', ctx_pct: 34, ctx_level: 'caution' as const, vpn: 'up' as const }

describe('statusParts', () => {
  it('orders model, ctx and vpn, without the ticket', () => {
    expect(statusText(statusParts(sl)!)).toBe('Opus 5.5 · 34% · VPN ●')
  })
  it('omits unknown ctx and hidden vpn', () => {
    const p = statusParts({ ...sl, ctx_pct: null, ctx_level: 'unknown', vpn: null })!
    expect(statusText(p)).toBe('Opus 5.5')
  })
  it('uses the board ctx (pct and tokens) when there is one', () => {
    const ctx = { pct: 18, tokens: 179_402, window: 1_000_000, fuente: 'statusline' as const, compactaciones: 0, ultima_compactacion: null }
    expect(statusText(statusParts(sl, ctx)!)).toBe('Opus 5.5 · 18% · 179k · VPN ●')
  })
  it('has no alarm level in the parts', () => {
    expect(statusParts(sl)!.ctx).toEqual({ text: '34%' })
  })
  it('is null without data', () => {
    expect(statusParts(null)).toBeNull()
  })
})

describe('normalizeStatusLine', () => {
  it('tolerates garbage', () => {
    expect(normalizeStatusLine(null)).toEqual({ model: '', ticket: '', ctx_pct: null, ctx_level: 'unknown', vpn: null })
    expect(normalizeStatusLine({ ctx_pct: 'x', ctx_level: 'warn', vpn: 'maybe' }).ctx_level).toBe('unknown')
  })
  it('rounds pct and validates level', () => {
    const n = normalizeStatusLine({ model: 'Opus 5.5', ctx_pct: 33.6, ctx_level: 'warn', vpn: 'down' })
    expect(n).toMatchObject({ ctx_pct: 34, ctx_level: 'warn', vpn: 'down' })
  })
})
