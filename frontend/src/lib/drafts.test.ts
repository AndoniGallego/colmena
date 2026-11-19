import { describe, expect, it } from 'vitest'
import { DRAFT_MAX_AGE_MS, DRAFT_MAX_CHARS, DRAFT_MAX_KEYS, getDraft, putDraft, sessionDraft } from './drafts'

describe('drafts', () => {
  it('guarda y recupera por clave', () => {
    const d = putDraft({}, 'a', 'hola', 1000)
    expect(getDraft(d, 'a', 1000)).toBe('hola')
    expect(getDraft(d, 'b', 1000)).toBe('')
  })
  it('solo espacios borra la clave', () => {
    const d = putDraft(putDraft({}, 'a', 'hola', 1), 'a', ' \n ', 2)
    expect(d).toEqual({})
  })
  it('recorta el texto', () => {
    const d = putDraft({}, 'a', 'x'.repeat(DRAFT_MAX_CHARS + 50), 1)
    expect(d.a.t).toHaveLength(DRAFT_MAX_CHARS)
  })
  it('descarta los de más de 7 días', () => {
    const old = { a: { t: 'viejo', ts: 0 } }
    expect(getDraft(old, 'a', DRAFT_MAX_AGE_MS + 1)).toBe('')
    expect(putDraft(old, 'b', 'nuevo', DRAFT_MAX_AGE_MS + 1)).not.toHaveProperty('a')
  })
  it('limita la cantidad y suelta los más viejos', () => {
    let d = {}
    for (let i = 0; i < DRAFT_MAX_KEYS + 5; i++) d = putDraft(d, `k${i}`, 'x', 10 + i)
    expect(Object.keys(d)).toHaveLength(DRAFT_MAX_KEYS)
    expect(d).not.toHaveProperty('k0')
    expect(d).toHaveProperty(`k${DRAFT_MAX_KEYS + 4}`)
  })
  it('ignora entradas corruptas', () => {
    const bad = { a: null, b: { t: 5, ts: 1 } } as never
    expect(getDraft(bad, 'a', 2)).toBe('')
    expect(putDraft(bad, 'c', 'ok', 2)).toEqual({ c: { t: 'ok', ts: 2 } })
  })
  it('clave de sesión', () => {
    expect(sessionDraft('p1')).toBe('s:p1')
  })
})
