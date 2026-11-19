import { describe, expect, it } from 'vitest'
import { bloquearRedEnDemo } from './demoActual'

describe('bloquearRedEnDemo', () => {
  it('cualquier fetch recibe un 404 y no toca la red', async () => {
    const win = { fetch: (() => Promise.reject(new Error('salió a la red'))) as typeof fetch }
    bloquearRedEnDemo(win)
    const r = await win.fetch('/api/sesiones')
    expect(r.status).toBe(404)
    expect((await win.fetch('https://example.com/x')).status).toBe(404)
  })
})
