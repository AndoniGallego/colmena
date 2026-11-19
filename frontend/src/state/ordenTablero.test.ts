import { readFileSync } from 'node:fs'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'

const putOrden = vi.fn()
const putOrdenPestanas = vi.fn()
const putPlegadas = vi.fn()
const putSilencio = vi.fn()

vi.mock('./app', () => ({
  auth: { value: 'ready' },
  ordenTableroEvent: { value: null },
  ordenPestanasEvent: { value: null },
  plegadasEvent: { value: null },
  silenciadasEvent: { value: null },
  setOrdenTablero: (...a: unknown[]) => putOrden(...a),
  setOrdenPestanas: (...a: unknown[]) => putOrdenPestanas(...a),
  setPlegadas: (...a: unknown[]) => putPlegadas(...a),
  setSilencio: (...a: unknown[]) => putSilencio(...a),
  getOrdenTablero: vi.fn(async () => ({ orden: [], pestanas: {}, plegadas: [] })),
}))

const {
  ordenError,
  plegadasError,
  ordenGuardado,
  ordenPestanasGuardado,
  plegadasGuardado,
  silenciadasGuardado,
  silencioError,
  silenciarSesion,
  guardarOrden,
  guardarOrdenPestanas,
  guardarPlegadas,
  cargarOrdenTablero,
  plegadasIguales,
} = await import('./ordenTablero')

describe('ordenTablero', () => {
  beforeEach(() => {
    putOrden.mockReset()
    putOrdenPestanas.mockReset()
    ordenGuardado.value = []
    ordenPestanasGuardado.value = {}
    ordenError.value = ''
  })

  it('carga orden del servidor', async () => {
    putOrden.mockResolvedValueOnce(undefined)
    await cargarOrdenTablero()
    expect(ordenGuardado.value).toEqual([])
  })

  it('revierte y guarda ordenError si falla guardarOrden', async () => {
    ordenGuardado.value = ['a']
    putOrden.mockRejectedValueOnce(new ApiError(500, 'x'))
    await guardarOrden(['b', 'a'])
    expect(ordenGuardado.value).toEqual(['a'])
    expect(ordenError.value).toBe('No pude guardar el orden')
  })

  it('revierte y guarda ordenError si falla guardarOrdenPestanas', async () => {
    ordenPestanasGuardado.value = { g1: ['t1'] }
    putOrdenPestanas.mockRejectedValueOnce(new ApiError(500, 'x'))
    await guardarOrdenPestanas('g1', ['t2', 't1'])
    expect(ordenPestanasGuardado.value).toEqual({ g1: ['t1'] })
    expect(ordenError.value).toBe('No pude guardar el orden')
  })

  it('SSE plegadas idénticas no reescribe el estado', () => {
    expect(plegadasIguales(['w1', 'w2'], ['w1', 'w2'])).toBe(true)
    plegadasGuardado.value = ['w1', 'w2']
    const refBefore = plegadasGuardado.value
    const next = ['w1', 'w2']
    if (!plegadasIguales(plegadasGuardado.value, next)) plegadasGuardado.value = next
    expect(plegadasGuardado.value).toBe(refBefore)
    const src = readFileSync('src/state/ordenTablero.ts', 'utf8')
    expect(src).toMatch(/plegadasIguales\(plegadasGuardado\.value, next\)/)
  })

  it('revierte plegadas si falla guardarPlegadas', async () => {
    plegadasGuardado.value = ['w1']
    putPlegadas.mockRejectedValueOnce(new ApiError(500, 'x'))
    await guardarPlegadas(['w1', 'w2'])
    expect(plegadasGuardado.value).toEqual(['w1'])
    expect(plegadasError.value).toBe('No pude guardar si está plegada')
  })
})

describe('silenciadas', () => {
  beforeEach(() => {
    putSilencio.mockReset()
    silenciadasGuardado.value = []
    silencioError.value = null
  })

  it('al tocar actualiza al instante y llama a la API con sid y valor', async () => {
    let fin!: () => void
    putSilencio.mockReturnValueOnce(new Promise<void>((r) => (fin = r)))
    const p = silenciarSesion('s1', true)
    expect(silenciadasGuardado.value).toEqual(['s1'])
    expect(putSilencio).toHaveBeenCalledWith('s1', true)
    fin()
    await p
    expect(silenciadasGuardado.value).toEqual(['s1'])
  })

  it('quita el silencio', async () => {
    silenciadasGuardado.value = ['s1', 's2']
    putSilencio.mockResolvedValueOnce(undefined)
    await silenciarSesion('s1', false)
    expect(silenciadasGuardado.value).toEqual(['s2'])
  })

  it('vuelve atrás si el PUT falla', async () => {
    silenciadasGuardado.value = ['s2']
    putSilencio.mockRejectedValueOnce(new ApiError(500, 'x'))
    await silenciarSesion('s1', true)
    expect(silenciadasGuardado.value).toEqual(['s2'])
    putSilencio.mockRejectedValueOnce(new ApiError(500, 'x'))
    await silenciarSesion('s2', false)
    expect(silenciadasGuardado.value).toEqual(['s2'])
  })

  it('si el PUT falla avisa en la fila de esa sesión y el próximo toque lo limpia', async () => {
    putSilencio.mockRejectedValueOnce(new ApiError(500, 'x'))
    await silenciarSesion('s1', true)
    expect(silencioError.value).toEqual({ sid: 's1', texto: 'No pude cambiar el silencio' })
    putSilencio.mockResolvedValueOnce(undefined)
    await silenciarSesion('s1', true)
    expect(silencioError.value).toBeNull()
  })

  it('un 401 vuelve atrás sin error propio (lo maneja el login)', async () => {
    putSilencio.mockRejectedValueOnce(new ApiError(401, 'x'))
    await silenciarSesion('s1', true)
    expect(silenciadasGuardado.value).toEqual([])
    expect(silencioError.value).toBeNull()
  })

  it('carga las silenciadas del servidor', async () => {
    const app = await import('./app')
    vi.mocked(app.getOrdenTablero).mockResolvedValueOnce({ orden: [], pestanas: {}, plegadas: [], silenciadas: ['z'] })
    await cargarOrdenTablero()
    expect(silenciadasGuardado.value).toEqual(['z'])
  })
})
