import { afterEach, describe, expect, it, vi } from 'vitest'

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
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
    platform: 'Win32',
    maxTouchPoints: 0,
  })
  vi.stubGlobal('Notification', {
    permission: 'default',
    requestPermission: vi.fn().mockResolvedValue('granted'),
  })
}

async function fresh() {
  vi.resetModules()
  return import('./push')
}

afterEach(() => vi.unstubAllGlobals())

describe('push en el programa de Windows', () => {
  it('en el programa queda en "programa" y no pide permiso', async () => {
    stubs('?app=windows')
    const { pushState, refreshPush, enablePush } = await fresh()
    await refreshPush()
    expect(pushState.status).toBe('programa')
    expect(await enablePush()).toBe(false)
    expect(Notification.requestPermission).not.toHaveBeenCalled()
  })

  it('fuera del programa no cambia', async () => {
    stubs('')
    const { pushState, refreshPush } = await fresh()
    await refreshPush()
    expect(pushState.status).toBe('unsupported')
  })
})
