import { describe, expect, it } from 'vitest'
import { normalizeCtx, normalizeTranscript } from '../api/normalize'
import type { AgentCtx } from '../api/types'
import { compactText, ctxLabel, ctxLine, ctxShort, fmtTokens, ringFraction } from './contexto'

const base: AgentCtx = { pct: 18, tokens: 179_402, window: 1_000_000, fuente: 'statusline', compactaciones: 0, ultima_compactacion: null }
const NOW = Date.parse('2026-11-01T16:00:00Z')

describe('fmtTokens', () => {
  it('abbreviates', () => {
    expect([fmtTokens(999), fmtTokens(179_402), fmtTokens(1_000_000), fmtTokens(1_500_000), fmtTokens(22_618)]).toEqual(['999', '179k', '1M', '1,5M', '23k'])
  })
})

describe('texto del anillo', () => {
  it('label y short sin avisos', () => {
    expect(ctxLabel(base)).toBe('18%')
    expect(ctxShort(base)).toBe('18% · 179k')
  })
  it('linea completa sin compactaciones', () => {
    expect(ctxLine(base, NOW)).toBe('179k de 1M tokens')
  })
  it('linea completa con compactaciones', () => {
    const c = { ...base, compactaciones: 2, ultima_compactacion: { ts: '2026-11-01T13:00:00Z', trigger: 'auto' as const, pre: 228_986, post: 22_618 } }
    expect(ctxLine(c, NOW)).toBe('179k de 1M tokens · compactada 2 veces, la última hace 3 h (229k → 23k)')
    expect(ctxLine({ ...c, compactaciones: 1 }, NOW)).toContain('compactada 1 vez,')
  })
  it('compactText', () => expect(compactText({ pre: 229_000, post: 22_600 })).toBe('229k → 23k'))
  it('ringFraction acota', () => {
    expect(ringFraction({ ...base, pct: 150 })).toBe(1)
    expect(ringFraction(null)).toBe(0)
    expect(ringFraction(base)).toBeCloseTo(0.18)
  })
})

describe('normalizeCtx', () => {
  const ok = { pct: 18, tokens: 179_402, window: 1_000_000, fuente: 'transcript', compactaciones: 2, ultima_compactacion: { ts: 't', trigger: 'manual', pre: 5, post: 1 } }
  it('acepta un ctx valido', () => expect(normalizeCtx(ok)).toMatchObject({ pct: 18, fuente: 'transcript', ultima_compactacion: { trigger: 'manual', pre: 5, post: 1 } }))
  it('descarta invalidos', () => {
    for (const bad of [null, {}, { ...ok, pct: -1 }, { ...ok, pct: 1.5 }, { ...ok, tokens: 0 }, { ...ok, window: 'x' }, { ...ok, fuente: 'otro' }]) expect(normalizeCtx(bad)).toBeNull()
  })
  it('acota pct a 999 y tolera compactacion rota', () => {
    const n = normalizeCtx({ ...ok, pct: 5000, compactaciones: 'x', ultima_compactacion: { pre: -1, post: 2 } })!
    expect(n.pct).toBe(999)
    expect(n.compactaciones).toBe(0)
    expect(n.ultima_compactacion).toBeNull()
  })
  it('no deja pasar claves de nivel de alarma', () => {
    expect(Object.keys(normalizeCtx({ ...ok, level: 'warn' })!)).not.toContain('level')
  })
})

describe('transcript compact', () => {
  it('lleva disparador y tamanos al separador', () => {
    const page = normalizeTranscript({ items: [{ kind: 'compact', text: 'r', ts: 't', compact: { trigger: 'auto', pre: 229_000, post: 22_600 } }, { kind: 'user', text: 'x', compact: { trigger: 'auto', pre: 1, post: 1 } }] })
    expect(page.items[0].compact).toEqual({ trigger: 'auto', pre: 229_000, post: 22_600 })
    expect(page.items[1].compact).toBeUndefined()
  })
})
