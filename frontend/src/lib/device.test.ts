import { describe, expect, it } from 'vitest'
import { deviceId } from './device'

const memoria = () => {
  const m = new Map<string, string>()
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v), m }
}

describe('deviceId', () => {
  it('en el notch es estable: una recarga reusa el mismo id', () => {
    const s = memoria()
    const a = deviceId(true, s)
    expect(a).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
    expect(deviceId(true, s)).toBe(a)
  })

  it('fuera del notch es nuevo en cada llamada y no guarda nada', () => {
    const s = memoria()
    expect(deviceId(false, s)).not.toBe(deviceId(false, s))
    expect(s.m.size).toBe(0)
  })

  it('un id guardado inválido se reemplaza', () => {
    const s = memoria()
    s.setItem('orq-device-notch', 'no válido!')
    const a = deviceId(true, s)
    expect(a).not.toBe('no válido!')
    expect(deviceId(true, s)).toBe(a)
  })

  it('sin sessionStorage (tira) cae al aleatorio', () => {
    const roto = {
      getItem: () => {
        throw new Error('x')
      },
      setItem: () => {
        throw new Error('x')
      },
    }
    expect(deviceId(true, roto)).toMatch(/^[A-Za-z0-9_-]{8,64}$/)
  })
})
