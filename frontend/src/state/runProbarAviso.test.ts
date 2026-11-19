import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'

const probarAviso = vi.fn()

vi.mock('../api/pushApi', () => ({
  httpPushApi: {
    key: vi.fn(),
    subscribe: vi.fn(),
    unsubscribe: vi.fn(),
    test: vi.fn(),
    testCierre: vi.fn(),
    probarAviso: (...a: unknown[]) => probarAviso(...a),
  },
}))

function memoria() {
  const store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v
    },
  }
}

function stubs(search: string) {
  vi.stubGlobal('location', { search })
  vi.stubGlobal('localStorage', memoria())
  vi.stubGlobal('sessionStorage', memoria())
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener() {} }))
  vi.stubGlobal('window', {
    isSecureContext: true,
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    PushManager: class {},
  })
  vi.stubGlobal('navigator', {
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64)',
    platform: 'Linux',
    maxTouchPoints: 0,
  })
  vi.stubGlobal('Notification', {
    permission: 'default',
    requestPermission: vi.fn().mockResolvedValue('granted'),
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('runProbarAviso', () => {
  beforeEach(() => {
    probarAviso.mockReset()
  })

  it('llama al API con kind y destino', async () => {
    stubs('')
    probarAviso.mockResolvedValue(undefined)
    vi.resetModules()
    const { runProbarAviso } = await import('./push')
    const r = await runProbarAviso('blocked', 'notch')
    expect(r).toEqual({ ok: true })
    expect(probarAviso).toHaveBeenCalledWith('blocked', 'notch')
  })

  it('traduce falta de suscriptos a mensaje de UI', async () => {
    stubs('')
    probarAviso.mockRejectedValue(new Error('no hay dispositivos suscriptos'))
    vi.resetModules()
    const { runProbarAviso } = await import('./push')
    const r = await runProbarAviso('asks', 'celu')
    expect(r).toEqual({ ok: false, message: 'No hay celus suscriptos' })
  })
})
