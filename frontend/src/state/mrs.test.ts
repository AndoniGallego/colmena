import { nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.hoisted(() => {
  vi.stubGlobal('location', { search: '', pathname: '/', hash: '' })
})

vi.mock('./app', () => ({
  auth: { value: 'ready' },
  mrsEvent: { value: 0 },
}))

vi.mock('./avisos', () => ({ marcarDestino: vi.fn() }))
vi.mock('../lib/viewport', () => ({ desktop: { value: true } }))
vi.mock('../lib/historyEntry', () => ({ historyEntry: () => ({ push: vi.fn(), back: vi.fn(() => false) }) }))

import type { Mr } from '../api/mrsApi'
const { httpMrsApi, normalizeMr } = await import('../api/mrsApi')
const { cargarDetalle, cargarMrs, cerrarDestino, elegirDestino, enPausa, envio, mandarASesion, mrsDestino, mrs, mrsVisible, pausar, pedirActualizacion, pendientesMrs, sesionDeMr, setMrsApi, visibles } = await import('./mrs')
const { normalizeDetalle } = await import('../api/mrsApi')

function mk(partial: Partial<Mr> & { ref: string; rol?: 'autor' | 'revisor'; pausado?: boolean }): Mr {
  const { ref, rol, pausado, ...rest } = partial
  const base = normalizeMr({
    project_id: 7,
    iid: 1,
    repo: 'g/r',
    repo_corto: 'r',
    titulo: 'feat: x',
    rama: 'feature/x',
    target: 'main',
    rol: rol ?? 'revisor',
    sha: 'a'.repeat(40),
    pipeline: { estado: 'ok', id: 1, url: '' },
    pausado: pausado ?? false,
    ref,
    ...rest,
  })!
  return base
}

describe('mrs pausa', () => {
  beforeEach(() => {
    mrs.items = []
    mrs.filtro = 'todos'
    mrs.busy = null
    mrs.detalle = null
    setMrsApi(httpMrsApi)
  })

  it('pendientesMrs y visibles ignoran pausados', () => {
    mrs.items = [
      mk({ ref: '8:2', rol: 'revisor', pausado: true, aprobaciones: { dadas: 0, requeridas: 1, faltan: 1, por: [], yo: false, puedo: true } }),
      mk({ ref: '9:3', rol: 'revisor', pausado: false, aprobaciones: { dadas: 0, requeridas: 1, faltan: 1, por: [], yo: false, puedo: true } }),
    ]
    expect(pendientesMrs.value).toBe(1)
    expect(visibles.value.map((m) => m.ref)).toEqual(['9:3'])
    expect(enPausa.value.map((m) => m.ref)).toEqual(['8:2'])
  })

  it('enPausa respeta el filtro', () => {
    mrs.items = [
      mk({ ref: '7:1', rol: 'autor', pausado: true }),
      mk({ ref: '8:2', rol: 'revisor', pausado: true }),
    ]
    mrs.filtro = 'revisor'
    expect(enPausa.value.map((m) => m.ref)).toEqual(['8:2'])
  })

  it('pausar optimista con rollback si falla el api', async () => {
    mrs.items = [mk({ ref: '7:1', rol: 'autor', pausado: false })]
    setMrsApi({
      pausar: vi.fn().mockRejectedValue(new Error('red')),
    } as any)
    const ok = await pausar('7:1', true)
    expect(ok).toBe(false)
    expect(mrs.items[0].pausado).toBe(false)

    setMrsApi({ pausar: vi.fn().mockResolvedValue(undefined) } as any)
    const ok2 = await pausar('7:1', true)
    expect(ok2).toBe(true)
    expect(mrs.items[0].pausado).toBe(true)
  })

  it('pausar invalida un cargarMrs en vuelo', async () => {
    mrs.items = [mk({ ref: '7:1', rol: 'autor', pausado: false })]
    let resolveListado: (v: unknown) => void = () => undefined
    setMrsApi({
      listar: () => new Promise((r) => (resolveListado = r)),
      pausar: vi.fn().mockResolvedValue(undefined),
    } as any)
    const carga = cargarMrs(true)
    await pausar('7:1', true)
    resolveListado({ items: [mk({ ref: '7:1', rol: 'autor', pausado: false })], error: '', actualizado: 0, refrescando: false, disponible: true, habilitado: true, sesiones: {}, version: 2 })
    await carga
    expect(mrs.items[0].pausado).toBe(true)
  })
})


const detalleDe = (ref: string, descripcion: string) =>
  normalizeDetalle({ ref, project_id: 7, iid: 1, rama: 'f/x', target: 'main', rol: 'autor', descripcion, jobs: [], hilos: [], actividad: [], archivos: [] })!

describe('detalle con cache', () => {
  beforeEach(() => {
    mrs.items = [mk({ ref: '7:1', rol: 'autor' })]
    mrs.detalle = null
    mrs.detLoading = false
    mrs.busy = null
  })

  it('al reabrir un MR muestra el detalle anterior al instante y lo refresca atrás', async () => {
    setMrsApi({ detalle: vi.fn().mockResolvedValue(detalleDe('7:1', 'viejo')) } as any)
    await cargarDetalle('7:1')
    mrs.detalle = null // se cerró el MR
    let responder: (v: unknown) => void = () => undefined
    setMrsApi({ detalle: vi.fn(() => new Promise((r) => (responder = r))) } as any)
    const carga = cargarDetalle('7:1')
    expect((mrs.detalle as { descripcion: string } | null)?.descripcion).toBe('viejo')
    expect(mrs.detLoading).toBe(false)
    responder(detalleDe('7:1', 'nuevo'))
    await carga
    expect((mrs.detalle as { descripcion: string } | null)?.descripcion).toBe('nuevo')
  })

  it('no mezcla el detalle de otro MR', async () => {
    setMrsApi({ detalle: vi.fn().mockResolvedValue(detalleDe('7:1', 'viejo')) } as any)
    await cargarDetalle('7:1')
    mrs.detalle = null
    setMrsApi({ detalle: vi.fn(() => new Promise(() => undefined)) } as any)
    void cargarDetalle('8:2')
    expect(mrs.detalle).toBeNull()
    expect(mrs.detLoading).toBe(true)
  })
})

describe('volver a la vista', () => {
  it('no vuelve a pedir la lista si recién se cargó', async () => {
    const listar = vi.fn().mockResolvedValue({ items: [], error: '', actualizado: 1, refrescando: false, disponible: true, habilitado: true, sesiones: {} })
    setMrsApi({ listar } as any)
    mrsVisible.value = false
    await cargarMrs(true)
    expect(listar).toHaveBeenCalledTimes(1)
    mrsVisible.value = true
    await nextTick()
    expect(listar).toHaveBeenCalledTimes(1)
  })
})

describe('pedirle a la sesión', () => {
  beforeEach(() => {
    mrs.sesiones = { 'sess-a': '7:1' }
    mrs.busy = null
    mrs.errConfirm = ''
    mrs.okMsg = ''
  })

  it('sesionDeMr encuentra la sesión asociada al MR', () => {
    expect(sesionDeMr('7:1')).toBe('sess-a')
    expect(sesionDeMr('9:9')).toBeNull()
  })

  it('manda el pedido y avisa que salió', async () => {
    const pedirActualizar = vi.fn().mockResolvedValue(undefined)
    setMrsApi({ pedirActualizar, detalle: vi.fn().mockResolvedValue(detalleDe('7:1', 'x')) } as any)
    expect(await pedirActualizacion('7:1')).toBe(true)
    expect(pedirActualizar).toHaveBeenCalledWith('7:1')
    expect(mrs.okMsg).toBe('Se lo pedí a la sesión.')
  })

  it('si la sesión no puede, deja el texto del servidor', async () => {
    const { ApiError } = await import('../api/types')
    setMrsApi({ pedirActualizar: vi.fn().mockRejectedValue(new ApiError(409, 'La sesión está trabajando: esperá a que termine.')) } as any)
    expect(await pedirActualizacion('7:1')).toBe(false)
    expect(mrs.errConfirm).toBe('La sesión está trabajando: esperá a que termine.')
    expect(mrs.okMsg).toBe('')
  })
})


describe('mandar a la sesión', () => {
  const dest = (...sesiones: Array<{ id: string; asociada: boolean }>) => ({
    sugerida: sesiones.find((x) => x.asociada)?.id ?? null,
    sesiones: sesiones.map((x) => ({ session_id: x.id, pane_id: 'w1:p1', nombre: x.id, status: 'idle', carpeta_corta: '', asociada: x.asociada })),
  })

  beforeEach(() => {
    vi.useFakeTimers()
    mrs.items = [mk({ ref: '7:1', rol: 'autor' })]
    envio.cual = ''
    envio.hecho = ''
    envio.error = { clave: '', msg: '' }
    cerrarDestino()
  })
  afterEach(() => vi.useRealTimers())

  it('con una sola sesión asociada manda directo y marca «mandado» 3 segundos', async () => {
    const jobASesion = vi.fn().mockResolvedValue(undefined)
    setMrsApi({ destinos: vi.fn().mockResolvedValue(dest({ id: 'sess-a', asociada: true }, { id: 'sess-b', asociada: false })), jobASesion } as any)
    await mandarASesion('7:1', { tipo: 'job', id: 900 })
    expect(jobASesion).toHaveBeenCalledWith('7:1', 900, 'sess-a')
    expect(mrsDestino.open).toBe(false)
    expect(envio.hecho).toBe('job:900')
    vi.advanceTimersByTime(3100)
    expect(envio.hecho).toBe('')
  })

  it('con varias o ninguna asociada abre la hoja con la sugerida primero y no manda', async () => {
    const hiloASesion = vi.fn().mockResolvedValue(undefined)
    setMrsApi({ destinos: vi.fn().mockResolvedValue(dest({ id: 'sess-a', asociada: false }, { id: 'sess-b', asociada: false })), hiloASesion } as any)
    await mandarASesion('7:1', { tipo: 'hilo', id: 'ab12cd34' })
    expect(mrsDestino.open).toBe(true)
    expect(mrsDestino.sesiones.map((x) => x.session_id)).toEqual(['sess-a', 'sess-b'])
    expect(hiloASesion).not.toHaveBeenCalled()
    await elegirDestino('sess-b')
    expect(hiloASesion).toHaveBeenCalledWith('7:1', 'ab12cd34', 'sess-b')
    expect(mrsDestino.open).toBe(false)
    expect(envio.hecho).toBe('hilo:ab12cd34')
  })

  it('sin sesiones abiertas avisa en el lugar y no abre la hoja', async () => {
    setMrsApi({ destinos: vi.fn().mockResolvedValue(dest()) } as any)
    await mandarASesion('7:1', { tipo: 'job', id: 900 })
    expect(mrsDestino.open).toBe(false)
    expect(envio.error).toEqual({ clave: 'job:900', msg: expect.stringContaining('No hay una sesión') })
  })

  it('si el servidor lo rechaza, deja el mensaje junto a ese botón', async () => {
    const { ApiError } = await import('../api/types')
    setMrsApi({
      destinos: vi.fn().mockResolvedValue(dest({ id: 'sess-a', asociada: true })),
      jobASesion: vi.fn().mockRejectedValue(new ApiError(409, 'La sesión está trabajando: esperá a que termine.')),
    } as any)
    await mandarASesion('7:1', { tipo: 'job', id: 900 })
    expect(envio.error).toEqual({ clave: 'job:900', msg: 'La sesión está trabajando: esperá a que termine.' })
    expect(envio.hecho).toBe('')
    expect(envio.cual).toBe('')
  })

  it('un error al elegir en la hoja la deja abierta con el mensaje', async () => {
    const { ApiError } = await import('../api/types')
    setMrsApi({
      destinos: vi.fn().mockResolvedValue(dest({ id: 'sess-a', asociada: false })),
      jobASesion: vi.fn().mockRejectedValue(new ApiError(404, 'Esa sesión ya no está abierta')),
    } as any)
    await mandarASesion('7:1', { tipo: 'job', id: 900 })
    await elegirDestino('sess-a')
    expect(mrsDestino.open).toBe(true)
    expect(mrsDestino.error).toBe('Esa sesión ya no está abierta')
  })

  it('ignora un segundo toque mientras se está mandando', async () => {
    let responder: (v: unknown) => void = () => undefined
    const destinos = vi.fn(() => new Promise((r) => (responder = r)))
    setMrsApi({ destinos } as any)
    const a = mandarASesion('7:1', { tipo: 'job', id: 900 })
    void mandarASesion('7:1', { tipo: 'job', id: 901 })
    expect(destinos).toHaveBeenCalledTimes(1)
    responder(dest())
    await a
  })
})
