import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'

const irAPcApi = vi.fn()
vi.mock('./app', () => ({ irAPc: (...a: unknown[]) => irAPcApi(...a) }))

const { irAPcSesion, irAPcEnviando, irAPcAviso } = await import('./irAPc')

describe('irAPcSesion', () => {
  beforeEach(() => {
    irAPcApi.mockReset()
    irAPcEnviando.value = {}
    irAPcAviso.value = null
    vi.useRealTimers()
  })

  it('llama a la API con el sid y avisa éxito', async () => {
    irAPcApi.mockResolvedValueOnce(undefined)
    await irAPcSesion('s1')
    expect(irAPcApi).toHaveBeenCalledWith('s1')
    expect(irAPcAviso.value).toEqual({ sid: 's1', texto: 'Abierta en la notebook', ok: true })
    expect(irAPcEnviando.value).toEqual({})
  })

  it('queda enviando mientras la API no responde', async () => {
    let fin!: () => void
    irAPcApi.mockReturnValueOnce(new Promise<void>((r) => (fin = r)))
    const p = irAPcSesion('s1')
    expect(irAPcEnviando.value).toEqual({ s1: true })
    fin()
    await p
    expect(irAPcEnviando.value).toEqual({})
  })

  it('enviar una sesión no bloquea a las otras', async () => {
    let fin!: () => void
    irAPcApi.mockReturnValueOnce(new Promise<void>((r) => (fin = r)))
    irAPcApi.mockResolvedValueOnce(undefined)
    const p = irAPcSesion('s1')
    await irAPcSesion('s2')
    expect(irAPcApi).toHaveBeenCalledTimes(2)
    expect(irAPcEnviando.value).toEqual({ s1: true })
    fin()
    await p
    expect(irAPcEnviando.value).toEqual({})
  })

  it('no lanza una segunda vez mientras envía', async () => {
    let fin!: () => void
    irAPcApi.mockReturnValueOnce(new Promise<void>((r) => (fin = r)))
    const p = irAPcSesion('s1')
    await irAPcSesion('s1')
    expect(irAPcApi).toHaveBeenCalledTimes(1)
    fin()
    await p
  })

  it('muestra el mensaje de error del backend', async () => {
    irAPcApi.mockRejectedValueOnce(new ApiError(409, 'Esta sesión no corre en una terminal de Colmena'))
    await irAPcSesion('s1')
    expect(irAPcAviso.value).toEqual({ sid: 's1', texto: 'Esta sesión no corre en una terminal de Colmena', ok: false })
    expect(irAPcEnviando.value).toEqual({})
  })

  it('error sin detalle usa un texto genérico y el 401 no avisa', async () => {
    irAPcApi.mockRejectedValueOnce(new Error('x'))
    await irAPcSesion('s1')
    expect(irAPcAviso.value?.texto).toBe('No pude abrir la notebook')
    irAPcAviso.value = null
    irAPcApi.mockRejectedValueOnce(new ApiError(401, 'no'))
    await irAPcSesion('s1')
    expect(irAPcAviso.value).toBeNull()
  })

  it('el aviso se va solo a los 3 s', async () => {
    vi.useFakeTimers()
    irAPcApi.mockResolvedValueOnce(undefined)
    await irAPcSesion('s1')
    expect(irAPcAviso.value).not.toBeNull()
    vi.advanceTimersByTime(3000)
    expect(irAPcAviso.value).toBeNull()
  })
})
