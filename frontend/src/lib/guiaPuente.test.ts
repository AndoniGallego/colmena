import { afterEach, describe, expect, it, vi } from 'vitest'
import { ErrorHttpGuia, MENSAJE_GUIA, pedirGuia, postGuia, salirGuia, siguienteGuia } from './guiaPuente'

const captura = {
  foto: 7,
  ventana: { titulo: 'Doc', proceso: 'word.exe' },
  controles: [{ n: 1, tipo: 'Button', nombre: 'Archivo' }],
  imagen: { tipo: 'png', ancho: 10, alto: 10, b64: 'AAAA' },
}
const invokeOk = () => vi.fn(async (cmd: string) => (cmd === 'nudo_mostrar' ? captura : 'ok'))

describe('pedirGuia', () => {
  it('limpia antes de mirar y postea G1 exacto', async () => {
    const invoke = invokeOk()
    const post = vi.fn().mockResolvedValue({ guia: 3, estado: 'preparando' })
    const r = await pedirGuia({ invoke, post, device: 'dev-1', pregunta: 'Cómo imprimo' })
    expect(invoke.mock.calls.map((c) => c[0])).toEqual(['nudo_limpiar', 'nudo_mostrar'])
    expect(post).toHaveBeenCalledWith('/api/guia/pedir', {
      device: 'dev-1',
      pregunta: 'Cómo imprimo',
      foto: { foto: 7, ventana: captura.ventana, controles: captura.controles },
      imagen: captura.imagen,
    })
    expect(r).toEqual({ ok: true, guia: 3, estado: 'preparando' })
  })
  it('si nudo_limpiar falla, sigue', async () => {
    const invoke = vi.fn(async (cmd: string) => {
      if (cmd === 'nudo_limpiar') throw 'fallo'
      return captura
    })
    const post = vi.fn().mockResolvedValue({ guia: 1, estado: 'mirando' })
    expect(await pedirGuia({ invoke, post, device: 'd', pregunta: 'x' })).toEqual({ ok: true, guia: 1, estado: 'mirando' })
  })
  it('invoke apagado no postea', async () => {
    const invoke = vi.fn(async (cmd: string) => {
      if (cmd === 'nudo_mostrar') throw 'apagado'
      return 'ok'
    })
    const post = vi.fn()
    expect(await pedirGuia({ invoke, post, device: 'd', pregunta: 'x' })).toEqual({ ok: false, error: 'apagado' })
    expect(post).not.toHaveBeenCalled()
  })
  it('invoke desconocido es fallo; captura inválida es fallo', async () => {
    const raro = vi.fn(async (cmd: string) => {
      if (cmd === 'nudo_mostrar') throw 'boom'
      return 'ok'
    })
    expect(await pedirGuia({ invoke: raro, post: vi.fn(), device: 'd', pregunta: 'x' })).toEqual({ ok: false, error: 'fallo' })
    const basura = vi.fn(async () => ({}))
    expect(await pedirGuia({ invoke: basura, post: vi.fn(), device: 'd', pregunta: 'x' })).toEqual({ ok: false, error: 'fallo' })
  })
  it.each([
    [new ErrorHttpGuia(409, 'reunion'), 'reunion'],
    [new ErrorHttpGuia(409, 'otra_pc'), 'otra_pc'],
    [new ErrorHttpGuia(409, 'mirando'), 'mirando'],
    [new ErrorHttpGuia(409, 'sin_guia'), 'sin_guia'],
    [new ErrorHttpGuia(422, 'sin_pregunta'), 'sin_pregunta'],
    [new ErrorHttpGuia(422, 'invalida'), 'invalida'],
    [new ErrorHttpGuia(413, null), 'grande'],
    [new ErrorHttpGuia(422, null), 'invalida'],
    [new ErrorHttpGuia(500, null), 'fallo'],
    [new ErrorHttpGuia(409, 'rara'), 'fallo'],
    [new TypeError('Failed to fetch'), 'sin_conexion'],
    [new Error('x'), 'fallo'],
  ])('error HTTP %# se mapea', async (err, esperado) => {
    const post = vi.fn().mockRejectedValue(err)
    expect(await pedirGuia({ invoke: invokeOk(), post, device: 'd', pregunta: 'x' })).toEqual({ ok: false, error: esperado })
  })
  it('respuesta sin guia entera es fallo', async () => {
    const post = vi.fn().mockResolvedValue({ nada: 1 })
    expect(await pedirGuia({ invoke: invokeOk(), post, device: 'd', pregunta: 'x' })).toEqual({ ok: false, error: 'fallo' })
  })
})

describe('siguienteGuia', () => {
  it('postea {device, foto, imagen} a /api/guia/siguiente', async () => {
    const invoke = invokeOk()
    const post = vi.fn().mockResolvedValue({ guia: 3, estado: 'mirando' })
    const r = await siguienteGuia({ invoke, post, device: 'dev-1' })
    expect(invoke.mock.calls.map((c) => c[0])).toEqual(['nudo_limpiar', 'nudo_mostrar'])
    expect(post).toHaveBeenCalledWith('/api/guia/siguiente', {
      device: 'dev-1',
      foto: { foto: 7, ventana: captura.ventana, controles: captura.controles },
      imagen: captura.imagen,
    })
    expect(r).toEqual({ ok: true, guia: 3, estado: 'mirando' })
  })
})

describe('salirGuia', () => {
  it('postea {device} a /api/guia/salir y no lanza', async () => {
    const post = vi.fn().mockResolvedValue({ ok: true })
    await salirGuia({ post, device: 'dev-1' })
    expect(post).toHaveBeenCalledWith('/api/guia/salir', { device: 'dev-1' })
    await expect(salirGuia({ post: vi.fn().mockRejectedValue(new Error('x')), device: 'd' })).resolves.toBeUndefined()
  })
})

describe('postGuia', () => {
  afterEach(() => vi.unstubAllGlobals())
  const resp = (status: number, body: unknown) => vi.fn().mockResolvedValue(new Response(JSON.stringify(body), { status }))
  it('devuelve el JSON si ok', async () => {
    vi.stubGlobal('fetch', resp(202, { guia: 1 }))
    expect(await postGuia('/api/guia/pedir', { a: 1 })).toEqual({ guia: 1 })
  })
  it('lee detail.codigo del error', async () => {
    vi.stubGlobal('fetch', resp(409, { detail: { codigo: 'reunion', mensaje: 'x' } }))
    await expect(postGuia('/u', {})).rejects.toMatchObject({ status: 409, codigo: 'reunion' })
  })
  it('sin codigo, codigo es null', async () => {
    vi.stubGlobal('fetch', resp(413, { detail: 'grande' }))
    await expect(postGuia('/u', {})).rejects.toMatchObject({ status: 413, codigo: null })
  })
})

describe('MENSAJE_GUIA', () => {
  it('textos exactos', () => {
    expect(MENSAJE_GUIA.reunion).toBe('Hay una reunión en curso: usá Mostrame del notch')
    expect(MENSAJE_GUIA.mirando).toBe('Todavía estoy mirando')
  })
})
