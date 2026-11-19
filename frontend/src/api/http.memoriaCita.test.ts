import { afterEach, describe, expect, it, vi } from 'vitest'
import { createHttpApi } from './http'

describe('getMemoriaCita', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('codifica el id de engram en la query', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      headers: new Headers(),
      clone() {
        return this
      },
      async json() {
        return {}
      },
    })
    vi.stubGlobal('fetch', fetchMock)
    const api = createHttpApi(vi.fn())
    await api.getMemoriaCita({ tipo: 'engram', id: 'a&b=c#d' } as never).catch(() => undefined)
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/memoria/cita?engram=a%26b%3Dc%23d')
  })
})
