import { describe, expect, it, vi } from 'vitest'
import { MENSAJE_MOSTRAR, mostrar, normalizarCaptura } from './mostrarPuente'

const captura = () => ({
  foto: 42,
  ventana: { titulo: 'Pedidos - Chrome', proceso: 'chrome.exe' },
  controles: [{ n: 1, tipo: 'boton', nombre: 'Guardar' }],
  imagen: { tipo: 'png', ancho: 1568, alto: 980, b64: 'iVBORw0KGgo' },
})

describe('normalizarCaptura', () => {
  it('acepta C1', () => {
    expect(normalizarCaptura(captura())?.foto).toBe(42)
  })
  it('rechaza un lado de 1569, tipo gif y b64 vacío', () => {
    expect(normalizarCaptura({ ...captura(), imagen: { ...captura().imagen, ancho: 1569 } })).toBeNull()
    expect(normalizarCaptura({ ...captura(), imagen: { ...captura().imagen, alto: 0 } })).toBeNull()
    expect(normalizarCaptura({ ...captura(), imagen: { ...captura().imagen, tipo: 'gif' } })).toBeNull()
    expect(normalizarCaptura({ ...captura(), imagen: { ...captura().imagen, b64: '' } })).toBeNull()
    expect(normalizarCaptura(null)).toBeNull()
    expect(normalizarCaptura({ foto: 1 })).toBeNull()
  })
})

const deps = (invoke: (c: string) => Promise<unknown>, post = vi.fn().mockResolvedValue({ linea: 'l7', estado: 'buscando' })) => ({
  invoke: vi.fn(invoke),
  post,
  reunion: 'r1',
  device: 'dev1',
  pregunta: '¿cómo exporto esto?',
})

describe('mostrar', () => {
  it('postea C2 exacto y devuelve la línea', async () => {
    const d = deps(async () => captura())
    const r = await mostrar(d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_mostrar')
    expect(d.post).toHaveBeenCalledWith('/api/reunion/mostrar', {
      reunion: 'r1',
      device: 'dev1',
      pregunta: '¿cómo exporto esto?',
      foto: { foto: 42, ventana: { titulo: 'Pedidos - Chrome', proceso: 'chrome.exe' }, controles: [{ n: 1, tipo: 'boton', nombre: 'Guardar' }] },
      imagen: { tipo: 'png', ancho: 1568, alto: 980, b64: 'iVBORw0KGgo' },
    })
    expect(r).toEqual({ ok: true, linea: 'l7' })
  })
  it('apagado en el invoke no postea', async () => {
    const d = deps(async () => {
      throw 'apagado'
    })
    expect(await mostrar(d)).toEqual({ ok: false, error: 'apagado' })
    expect(d.post).not.toHaveBeenCalled()
  })
  it('sin_ventana y error raro', async () => {
    expect(await mostrar(deps(async () => Promise.reject('sin_ventana')))).toEqual({ ok: false, error: 'sin_ventana' })
    expect(await mostrar(deps(async () => Promise.reject(new Error('x'))))).toEqual({ ok: false, error: 'fallo' })
  })
  it('captura rota da fallo', async () => {
    expect(await mostrar(deps(async () => ({ foto: 1 })))).toEqual({ ok: false, error: 'fallo' })
  })
  it('409 da ocupado, 413 da grande, otro da fallo', async () => {
    const con = (status: number) => deps(async () => captura(), vi.fn().mockRejectedValue(Object.assign(new Error(String(status)), { status })))
    expect(await mostrar(con(409))).toEqual({ ok: false, error: 'ocupado' })
    expect(await mostrar(con(413))).toEqual({ ok: false, error: 'grande' })
    expect(await mostrar(con(500))).toEqual({ ok: false, error: 'fallo' })
  })
  it('422 con la pregunta vacía da sin_pregunta; con pregunta, fallo', async () => {
    const con = () => deps(async () => captura(), vi.fn().mockRejectedValue(Object.assign(new Error('422'), { status: 422 })))
    expect(await mostrar({ ...con(), pregunta: '' })).toEqual({ ok: false, error: 'sin_pregunta' })
    expect(await mostrar({ ...con(), pregunta: 'x' })).toEqual({ ok: false, error: 'fallo' })
    expect(MENSAJE_MOSTRAR.sin_pregunta).toBe('Escribí qué querés que te muestre')
  })
  it('hay mensaje para cada error', () => {
    expect(MENSAJE_MOSTRAR.apagado).toBe('Prendé el nudo en la bandeja')
  })
})
