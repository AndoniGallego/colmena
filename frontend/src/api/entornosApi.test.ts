import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './types'
import {
  listarEntornos,
  normalizarEntornos,
  normalizarResultadoPrueba,
  probarEntorno,
  type PedidoPrueba,
} from './entornosApi'

describe('entornosApi', () => {
  const baseEntorno = { salud: null, apagado: false, servicios: [] as { servicio: string; estado: 'corriendo'; codigo: null; hace_s: null }[] }
  const ps9 = {
    nombre: 'ps9',
    carpeta: '~/proyectos/acme/ps9',
    principal: 8080,
    puertos: [
      { puerto: 8080, servicio: 'web', puerto_contenedor: 80, abrible: true },
      { puerto: 8092, servicio: 'mock-login', puerto_contenedor: 3000, abrible: true },
    ],
    ...baseEntorno,
  }

  it('normaliza con reglas de robustez', () => {
    const largo80 = 's'.repeat(80)
    const largo81 = 'x'.repeat(81)
    const largo301 = 'y'.repeat(301)
    const r = normalizarEntornos({
      entornos: [
        'no soy objeto',
        {
          nombre: 'ok',
          carpeta: largo301,
          principal: 8080,
          puertos: [
            { puerto: 8080.5, servicio: 'w', abrible: true },
            { puerto: 8092, servicio: largo81, puerto_contenedor: 3, abrible: 'true' },
            { puerto: 8093, servicio: largo80, puerto_contenedor: 65536, abrible: 1 },
            { puerto: NaN, servicio: 'n', abrible: true },
          ],
          extra: 1,
        },
        null,
      ],
      error: 42,
    })
    expect(r.error).toBeNull()
    expect(r.entornos).toHaveLength(1)
    const e = r.entornos[0]
    expect(e.puertos.map((p) => p.puerto)).toEqual([8092, 8093])
    expect(e.puertos[0].servicio).toBe('x'.repeat(80))
    expect(e.puertos[0].abrible).toBe(false)
    expect(e.puertos[1].puerto_contenedor).toBeNull()
    expect(e.carpeta).toBe('y'.repeat(300))
    expect(e.principal).toBeNull()
  })

  it('normaliza la respuesta y descarta lo inválido', () => {
    const r = normalizarEntornos({
      entornos: [
        ps9,
        { ...ps9, nombre: '../x' },
        {
          ...ps9,
          nombre: 'ok',
          principal: 9999,
          puertos: [{ puerto: 70000 }, { puerto: 'x' }],
        },
      ],
      error: null,
    })
    expect(r.entornos.map((e) => e.nombre)).toEqual(['ps9', 'ok'])
    expect(r.entornos[0]).toEqual(ps9)
    expect(r.entornos[1]).toMatchObject({ principal: null, puertos: [] })
    expect(normalizarEntornos(null)).toEqual({ entornos: [], error: null })
  })

  it('conserva el orden de los puertos tal como vienen', () => {
    const r = normalizarEntornos({
      entornos: [
        {
          nombre: 'x',
          carpeta: '',
          principal: 9002,
          puertos: [
            { puerto: 9002, servicio: 'a', puerto_contenedor: null, abrible: true },
            { puerto: 9001, servicio: 'b', puerto_contenedor: null, abrible: true },
          ],
        },
      ],
      error: null,
    })
    expect(r.entornos[0]!.puertos.map((p) => p.puerto)).toEqual([9002, 9001])
  })

  it('principal abrible false no cuenta', () => {
    const r = normalizarEntornos({
      entornos: [
        {
          nombre: 'x',
          carpeta: '',
          principal: 8080,
          puertos: [{ puerto: 8080, servicio: 'w', puerto_contenedor: null, abrible: false }],
        },
      ],
      error: null,
    })
    expect(r.entornos[0]!.principal).toBeNull()
  })

  it('normaliza salud, apagado y servicios con defaults y validación', () => {
    const r = normalizarEntornos({
      entornos: [
        {
          nombre: 'ok',
          carpeta: '',
          principal: null,
          puertos: [],
          salud: 'verde',
          apagado: true,
          servicios: [
            { servicio: 'migrate', estado: 'terminado', codigo: 0, hace_s: 3600 },
            { servicio: 'hs-api', estado: 'caido', codigo: 1, hace_s: 300 },
            { servicio: 'x', estado: 'muerto', codigo: -1, hace_s: 1.5 },
            { servicio: '', estado: 'corriendo', codigo: null, hace_s: null },
            'no',
          ],
        },
        { nombre: 'viejo', carpeta: '', principal: null, puertos: [], salud: 'azul' },
      ],
      error: null,
    })
    expect(r.entornos[0]).toMatchObject({
      salud: 'verde',
      apagado: true,
      servicios: [
        { servicio: 'migrate', estado: 'terminado', codigo: 0, hace_s: 3600 },
        { servicio: 'hs-api', estado: 'caido', codigo: 1, hace_s: 300 },
      ],
    })
    expect(r.entornos[1]).toMatchObject({ salud: null, apagado: false, servicios: [] })
  })

  const pedidoBase = (): PedidoPrueba => ({
    nombre: 'ps9',
    puerto: 8080,
    metodo: 'GET',
    ruta: '/',
    encabezados: [],
    cuerpo: null,
    confirmado: false,
  })

  const resultadoOk = {
    codigo: 200,
    ms: 42,
    tipo: 'application/json',
    encabezados: [['content-type', 'application/json']] as [string, string][],
    cuerpo: '{"a":1}',
    bytes: 7,
    truncado: false,
  }

  it('probarEntorno arma el POST correcto', async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify(resultadoOk), { status: 200 }))
    const p = pedidoBase()
    await probarEntorno(p, f)
    expect(f).toHaveBeenCalledWith(
      '/api/entornos/probar',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(p),
      }),
    )
  })

  it('probarEntorno lee error del 404', async () => {
    const f = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: 'Ese puerto no es de un entorno prendido' }), { status: 404 }),
    )
    await expect(probarEntorno(pedidoBase(), f)).rejects.toMatchObject({
      status: 404,
      detail: 'Ese puerto no es de un entorno prendido',
    })
  })

  it('probarEntorno conexión cortada', async () => {
    const f = vi.fn().mockRejectedValue(new TypeError('Failed to fetch'))
    await expect(probarEntorno(pedidoBase(), f)).rejects.toMatchObject({
      status: 0,
      detail: 'Se cortó la conexión con el servidor',
    })
  })

  it('normalizarResultadoPrueba inválido', () => {
    expect(() => normalizarResultadoPrueba({ codigo: 'x', ms: 1 })).toThrowError(
      expect.objectContaining({ detail: 'Respuesta inválida del servidor' }),
    )
    expect(() => normalizarResultadoPrueba({ ...resultadoOk, ms: -1 })).toThrowError(ApiError)
  })

  it('normalizarResultadoPrueba descarta encabezados mal formados', () => {
    const r = normalizarResultadoPrueba({
      ...resultadoOk,
      encabezados: [['ok', 'v'], 'malo', ['a', 'b', 'c'], 42],
    })
    expect(r.encabezados).toEqual([['ok', 'v'], ['a', 'b']])
  })

  it('pide /api/entornos con la cookie y un 401 es ApiError', async () => {
    const ok = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ entornos: [ps9], error: 'x' }), { status: 200 }),
    )
    expect(await listarEntornos(ok)).toEqual({ entornos: [ps9], error: 'x' })
    expect(ok).toHaveBeenCalledWith('/api/entornos', expect.objectContaining({ credentials: 'same-origin' }))
    const no = vi.fn().mockResolvedValue(new Response('{"detail":"no"}', { status: 401 }))
    await expect(listarEntornos(no)).rejects.toMatchObject({ status: 401 })
  })
})
