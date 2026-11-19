import { beforeEach, describe, expect, it, vi } from 'vitest'

const CLAVE = 'colmena.notas.cola'

function storageMemoria() {
  const m = new Map<string, string>()
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, v),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  }
}

async function cargar() {
  vi.resetModules()
  return import('./notasCola')
}

describe('notasCola', () => {
  beforeEach(() => {
    vi.stubGlobal('localStorage', storageMemoria())
  })

  it('manda en orden, frena en el primer fallo y no repite ninguna al reintentar', async () => {
    const { encolar, pendientesCola, vaciarCola } = await cargar()
    encolar({ tipo: 'recordatorio', texto: 'uno' })
    encolar({ tipo: 'apunte', texto: 'dos' })
    encolar({ tipo: 'recordatorio', texto: 'tres' })
    expect(pendientesCola()).toBe(3)
    expect(localStorage.getItem(CLAVE)).toContain('uno')

    const enviadas: string[] = []
    let n = 0
    const enferma = async (b: { texto: string }) => {
      n++
      if (n === 2) throw new TypeError('Failed to fetch')
      enviadas.push(b.texto)
    }
    expect(await vaciarCola(enferma)).toBe(1)
    expect(pendientesCola()).toBe(2)

    const sana = async (b: { texto: string }) => {
      enviadas.push(b.texto)
    }
    expect(await vaciarCola(sana)).toBe(2)
    expect(pendientesCola()).toBe(0)
    expect(enviadas).toEqual(['uno', 'dos', 'tres'])
  })

  it('dos vaciados a la vez no mandan la misma nota dos veces', async () => {
    const { encolar, vaciarCola } = await cargar()
    encolar({ tipo: 'apunte', texto: 'una' })
    const crear = vi.fn(async () => undefined)
    await Promise.all([vaciarCola(crear), vaciarCola(crear)])
    expect(crear).toHaveBeenCalledTimes(1)
  })

  it('con localStorage roto encolar no rompe y la nota queda en memoria', async () => {
    vi.stubGlobal('localStorage', {
      getItem() {
        throw new Error('SecurityError')
      },
      setItem() {
        throw new Error('QuotaExceeded')
      },
    })
    const { encolar, pendientesCola, vaciarCola } = await cargar()
    expect(() => encolar({ tipo: 'apunte', texto: 'igual' })).not.toThrow()
    expect(pendientesCola()).toBe(1)
    const crear = vi.fn(async () => undefined)
    expect(await vaciarCola(crear)).toBe(1)
    expect(pendientesCola()).toBe(0)
  })

  it('con datos rotos en la clave arranca vacía', async () => {
    localStorage.setItem(CLAVE, '{no es json')
    const { pendientesCola } = await cargar()
    expect(pendientesCola()).toBe(0)
  })

  it('esSinRed distingue la falta de red de un error del servidor', async () => {
    const { esSinRed } = await cargar()
    const { ApiError } = await import('../api/types')
    expect(esSinRed(new TypeError('Failed to fetch'))).toBe(true)
    expect(esSinRed(new ApiError(502, 'Bad Gateway'))).toBe(true)
    expect(esSinRed(new ApiError(422, 'Texto vacío'))).toBe(false)
    expect(esSinRed(new ApiError(500, 'boom'))).toBe(false)
    expect(esSinRed(new ApiError(401, 'Unauthorized'))).toBe(false)
  })
})
