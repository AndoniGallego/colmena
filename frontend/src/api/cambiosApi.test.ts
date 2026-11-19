import { afterEach, describe, expect, it, vi } from 'vitest'
import { getCambios, normalizeCambios } from './cambiosApi'
import { ApiError } from './types'

afterEach(() => vi.unstubAllGlobals())

describe('normalizeCambios', () => {
  it('normaliza y descarta basura', () => {
    const c = normalizeCambios({
      repo: true, rama: 'feature/x', base: 'main', commits_total: 3, sin_guardar: 1, truncado: true,
      commits: [{ sha: 'abc', titulo: 't' }, { sha: 5 }],
      archivos: [{ path: 'a.txt', estado: 'M', adds: 2, dels: 1, binario: false, diff: '@@', truncado: false }, { estado: 'M' }],
    })
    expect(c.repo).toBe(true)
    expect(c.rama).toBe('feature/x')
    expect(c.commits).toEqual([{ sha: 'abc', titulo: 't' }])
    expect(c.archivos).toHaveLength(1)
    expect(c.archivos[0]).toMatchObject({ path: 'a.txt', estado: 'M', adds: 2, dels: 1 })
    expect(c.truncado).toBe(true)
  })

  it('no repo', () => {
    expect(normalizeCambios({ repo: false }).repo).toBe(false)
    expect(normalizeCambios(null).archivos).toEqual([])
  })
})

describe('getCambios', () => {
  it('pide la ruta de la sesión y refresca a pedido', async () => {
    const f = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ repo: true, archivos: [] }) })
    vi.stubGlobal('fetch', f)
    await getCambios('abc 1', true)
    expect(f.mock.calls[0][0]).toBe('/api/sesiones/abc%201/cambios?refrescar=1')
    await getCambios('abc', false)
    expect(f.mock.calls[1][0]).toBe('/api/sesiones/abc/cambios')
  })

  it('devuelve el detalle del error', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 403, headers: new Headers(), json: async () => ({ detail: 'No permitida' }) }))
    await expect(getCambios('a')).rejects.toMatchObject({ status: 403, detail: 'No permitida' })
    await expect(getCambios('a')).rejects.toBeInstanceOf(ApiError)
  })
})
