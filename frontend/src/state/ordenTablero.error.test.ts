import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'

const putOrden = vi.fn()
const putOrdenPestanas = vi.fn()

vi.mock('./app', () => ({
  auth: { value: 'ready' },
  ordenTableroEvent: { value: null },
  ordenPestanasEvent: { value: null },
  setOrdenTablero: (...a: unknown[]) => putOrden(...a),
  setOrdenPestanas: (...a: unknown[]) => putOrdenPestanas(...a),
  getOrdenTablero: vi.fn(async () => ({ orden: [], pestanas: {}, plegadas: [] })),
}))

const { ordenError, guardarOrden, ordenGuardado } = await import('./ordenTablero')

describe('ordenTablero errores en el lugar', () => {
  beforeEach(() => {
    putOrden.mockReset()
    putOrdenPestanas.mockReset()
    ordenGuardado.value = []
    ordenError.value = ''
  })

  it('guarda error local al fallar guardarOrden', async () => {
    putOrden.mockRejectedValueOnce(new ApiError(500, 'x'))
    await guardarOrden(['a'])
    expect(ordenError.value).toBe('No pude guardar el orden')
  })
})
