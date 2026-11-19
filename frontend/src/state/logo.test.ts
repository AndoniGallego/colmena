import { afterEach, describe, expect, it, vi } from 'vitest'

function fakeStorage(init: Record<string, string> = {}) {
  const store = { ...init }
  vi.stubGlobal('localStorage', { getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => void (store[k] = v) })
  return store
}

async function fresh() {
  vi.resetModules()
  return import('./logo')
}

afterEach(() => vi.unstubAllGlobals())

describe('variante de logo', () => {
  it('sin nada guardado arranca con el panal', async () => {
    fakeStorage()
    expect((await fresh()).logoVariant.value).toBe('panal')
  })

  it('elegir una variante la aplica y la guarda', async () => {
    const store = fakeStorage()
    const m = await fresh()
    m.setLogo('abeja')
    expect(m.logoVariant.value).toBe('abeja')
    expect(JSON.parse(store['orq.logo'])).toBe('abeja')
    expect((await fresh()).logoVariant.value).toBe('abeja')
  })

  it('un valor guardado inválido vuelve al default', async () => {
    fakeStorage({ 'orq.logo': JSON.stringify('orbita') })
    expect((await fresh()).logoVariant.value).toBe('panal')
  })

  it('si el almacenamiento está bloqueado sigue andando en memoria', async () => {
    vi.stubGlobal('localStorage', {
      getItem: () => {
        throw new Error('blocked')
      },
      setItem: () => {
        throw new Error('blocked')
      },
    })
    const m = await fresh()
    expect(m.logoVariant.value).toBe('panal')
    expect(() => m.setLogo('monograma')).not.toThrow()
    expect(m.logoVariant.value).toBe('monograma')
  })
})
