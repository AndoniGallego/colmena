import { afterEach, describe, expect, it, vi } from 'vitest'
import { claveNo } from './telemetria'

afterEach(() => vi.unstubAllGlobals())

describe('claveNo', () => {
  it('devuelve 16 hex, estable entre llamadas y distinta por índice', async () => {
    const a = await claveNo('s', 'm', 0)
    expect(a).toMatch(/^[0-9a-f]{16}$/)
    expect(await claveNo('s', 'm', 0)).toBe(a)
    expect(await claveNo('s', 'm', 1)).not.toBe(a)
  })

  it('sin crypto.subtle (contexto no seguro) devuelve null', async () => {
    vi.stubGlobal('crypto', {})
    expect(await claveNo('s', 'm', 0)).toBeNull()
  })
})
