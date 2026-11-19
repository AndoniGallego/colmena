import { beforeEach, describe, expect, it, vi } from 'vitest'

const listarNotas = vi.fn()
const conexion = { ref: null as null | { value: { connection: string } } }

let S: typeof import('./notas')

const n = (id: string, creada_at: string) => ({ id, tipo: 'recordatorio', texto: id, hecha_at: null, creada_at, editada_at: creada_at, origen: null })
const resp = (version: number, ids: string[] = []) => ({ notas: ids.map((i) => n(i, '2026-11-18T10:00:00Z')), pendientes: ids.length, version })

beforeEach(async () => {
  vi.resetModules()
  listarNotas.mockReset()
  listarNotas.mockResolvedValue(resp(5))
  // Un ref nuevo por import: los watchers de módulos anteriores no deben escuchar el de este test.
  vi.doMock('./app', async () => {
    const { shallowRef } = await import('vue')
    conexion.ref = shallowRef({ connection: 'live' })
    return {
      boardState: conexion.ref,
      listarNotas: (...a: unknown[]) => listarNotas(...a),
      crearNotaApi: vi.fn(),
      editarNotaApi: vi.fn(),
      borrarNotaApi: vi.fn(),
    }
  })
  S = await import('./notas')
})

describe('onNotas', () => {
  it('con versión nueva recarga una vez; con la misma no', async () => {
    S.onNotas({ version: 5, pendientes: 2 })
    await vi.waitFor(() => expect(listarNotas).toHaveBeenCalledTimes(1))
    await vi.waitFor(() => expect(S.pendientes.value).toBe(0))
    S.onNotas({ version: 5, pendientes: 2 })
    await Promise.resolve()
    expect(listarNotas).toHaveBeenCalledTimes(1)
  })
  it('si la recarga falla, repetir la misma versión reintenta', async () => {
    listarNotas.mockRejectedValue(new Error('503'))
    S.onNotas({ version: 2, pendientes: 1 })
    await vi.waitFor(() => expect(listarNotas).toHaveBeenCalledTimes(1))
    await Promise.resolve()
    S.onNotas({ version: 2, pendientes: 1 })
    await vi.waitFor(() => expect(listarNotas).toHaveBeenCalledTimes(2))
    expect(S.pendientes.value).toBe(0)
  })
})

describe('reconexión', () => {
  it('al volver a live recarga, y un evento con la versión que ya tenía vuelve a recargar', async () => {
    listarNotas.mockResolvedValue(resp(1))
    await S.cargarNotas()
    listarNotas.mockClear()
    conexion.ref!.value = { connection: 'reconnecting' }
    await Promise.resolve()
    expect(listarNotas).not.toHaveBeenCalled()
    // El orquestador reinició: la versión del servidor volvió a 0 y la recarga de la reconexión falla.
    listarNotas.mockRejectedValueOnce(new Error('503'))
    conexion.ref!.value = { connection: 'live' }
    await vi.waitFor(() => expect(listarNotas).toHaveBeenCalledTimes(1))
    await Promise.resolve()
    listarNotas.mockResolvedValue(resp(1))
    S.onNotas({ version: 1, pendientes: 0 })
    await vi.waitFor(() => expect(listarNotas).toHaveBeenCalledTimes(2))
  })
})

describe('cargarNotas', () => {
  it('ordena las más nuevas primero y fija pendientes', async () => {
    listarNotas.mockResolvedValue({ notas: [n('a', '2026-11-18T10:00:00Z'), n('b', '2026-11-18T11:00:00Z')], pendientes: 2, version: 9 })
    await S.cargarNotas()
    expect(S.notas.value.map((x) => x.id)).toEqual(['b', 'a'])
    expect(S.pendientes.value).toBe(2)
  })
  it('si falla deja el estado anterior sin lanzar', async () => {
    listarNotas.mockResolvedValue(resp(3, ['x']))
    await S.cargarNotas()
    listarNotas.mockRejectedValue(new Error('503'))
    await expect(S.cargarNotas()).resolves.toBeUndefined()
    expect(S.notas.value.map((x) => x.id)).toEqual(['x'])
  })
  it('cargas superpuestas: la más nueva gana aunque la primera resuelva al final', async () => {
    let r1: (v: unknown) => void = () => {}
    listarNotas.mockImplementationOnce(() => new Promise((r) => (r1 = r)))
    listarNotas.mockResolvedValueOnce(resp(2, ['nuevo']))
    const p1 = S.cargarNotas()
    const p2 = S.cargarNotas()
    await p2
    r1(resp(1, ['viejo']))
    await p1
    expect(S.notas.value.map((x) => x.id)).toEqual(['nuevo'])
    S.onNotas({ version: 2, pendientes: 1 })
    await Promise.resolve()
    expect(listarNotas).toHaveBeenCalledTimes(2)
  })
})
