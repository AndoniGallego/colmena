import { describe, expect, it, vi } from 'vitest'
import { atenderOrdenNudo, COMANDOS, escucharSalirNudo, normalizarOrdenNudo, type OrdenNudo } from './nudoPuente'

const token = 't'.repeat(32)
const base = { id: 'abcdefgh', token, sesion: 'A' }
const orden = (op: OrdenNudo['op'], args: Record<string, unknown> = {}, guia = false): OrdenNudo => ({ ...base, op, args, guia })
const deps = (invoke: (c: string, a?: Record<string, unknown>) => Promise<unknown>) => ({ invoke: vi.fn(invoke), post: vi.fn().mockResolvedValue(undefined) })

describe('normalizarOrdenNudo', () => {
  it('normaliza una orden válida y descarta basura', () => {
    expect(normalizarOrdenNudo({ ...base, op: 'controles', args: {} })?.op).toBe('controles')
    expect(normalizarOrdenNudo({ id: 'x', token: 't', op: 'controles' })).toBeNull()
    expect(normalizarOrdenNudo({ ...base, op: 'borrar', args: {} })).toBeNull()
    expect(normalizarOrdenNudo(null)).toBeNull()
    expect(normalizarOrdenNudo({ ...base, op: 'estado', args: [] })?.args).toEqual({})
  })
  it('COMANDOS cubre todas las operaciones', () => {
    expect(COMANDOS.senalar).toBe('nudo_senalar')
  })
})

describe('atenderOrdenNudo', () => {
  it('controles: invoca nudo_controles y postea el resultado con device y token', async () => {
    const lista = { foto: 1, controles: [] }
    const d = deps(async () => lista)
    await atenderOrdenNudo(orden('controles'), 'dev12345', d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_controles', undefined)
    expect(d.post).toHaveBeenCalledWith('/api/nudo/abcdefgh/respuesta', { device: 'dev12345', token, resultado: lista })
  })
  it('senalar: pasa foto, n, texto, sesion y esperar, y postea {resultado}', async () => {
    const d = deps(async () => 'listo')
    await atenderOrdenNudo(orden('senalar', { foto: 7, n: 12, texto: 'Tocá Guardar', esperar: 120 }), 'dev12345', d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_senalar', { foto: 7, n: 12, texto: 'Tocá Guardar', sesion: 'A', esperar: 120 })
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ resultado: 'listo' })
  })
  it('senalar sin esperar no manda la clave', async () => {
    const d = deps(async () => 'ok')
    await atenderOrdenNudo(orden('senalar', { foto: 7, n: 1, texto: 'x', esperar: null }), 'dev12345', d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_senalar', { foto: 7, n: 1, texto: 'x', sesion: 'A' })
  })
  it('marcar: pasa foto, marcas y sesion', async () => {
    const d = deps(async () => 'ok')
    await atenderOrdenNudo(orden('marcar', { foto: 3, marcas: [{ n: 1, etiqueta: 'a' }] }), 'dev12345', d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_marcar', { foto: 3, marcas: [{ n: 1, etiqueta: 'a' }], sesion: 'A' })
  })
  it('estado devuelve el objeto tal cual', async () => {
    const e = { prendido: true, se_ve_al_compartir: false }
    const d = deps(async () => e)
    await atenderOrdenNudo(orden('estado'), 'dev12345', d)
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual(e)
  })
  it('un error conocido de la PC viaja como {error}', async () => {
    const d = deps(async () => Promise.reject('apagado'))
    await atenderOrdenNudo(orden('limpiar'), 'dev12345', d)
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ error: 'apagado' })
  })
  it('un error desconocido viaja como fallo_pc', async () => {
    const d = deps(async () => Promise.reject(new Error('boom')))
    await atenderOrdenNudo(orden('limpiar'), 'dev12345', d)
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ error: 'fallo_pc' })
  })
  it('un código del backend que no es de la PC también es fallo_pc', async () => {
    const d = deps(async () => Promise.reject('ocupado'))
    await atenderOrdenNudo(orden('limpiar'), 'dev12345', d)
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ error: 'fallo_pc' })
  })
  it('si el post falla no revienta pero deja un aviso en consola', async () => {
    const aviso = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const d = deps(async () => 'ok')
    d.post.mockRejectedValue(new Error('500'))
    await atenderOrdenNudo(orden('limpiar'), 'dev12345', d)
    expect(aviso).toHaveBeenCalledTimes(1)
    aviso.mockRestore()
  })
  it('si el post falla no revienta', async () => {
    const d = deps(async () => 'ok')
    d.post.mockRejectedValue(new Error('x'))
    await expect(atenderOrdenNudo(orden('limpiar'), 'dev12345', d)).resolves.toBeUndefined()
  })
})

describe('escucharSalirNudo', () => {
  it('salir de la PC postea /api/nudo/salir', async () => {
    let cb: () => void = () => {}
    const post = vi.fn().mockResolvedValue(undefined)
    await escucharSalirNudo('dev12345', { listen: (_e, f) => (cb = f), post })
    cb()
    expect(post).toHaveBeenCalledWith('/api/nudo/salir', { device: 'dev12345' })
  })
  it('sin listen no hace nada', async () => {
    await expect(escucharSalirNudo('dev12345', { post: vi.fn() })).resolves.toBeDefined()
  })
  it('devuelve true cuando quedó escuchando', async () => {
    await expect(escucharSalirNudo('dev12345', { listen: () => Promise.resolve(() => undefined), post: vi.fn() })).resolves.toBe(true)
  })
  it('sin listen devuelve false para que se reintente', async () => {
    await expect(escucharSalirNudo('dev12345', { post: vi.fn() })).resolves.toBe(false)
  })
  it('si listen rechaza o tira, avisa en consola y devuelve false sin romper', async () => {
    const aviso = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    await expect(escucharSalirNudo('dev12345', { listen: () => Promise.reject(new Error('x')), post: vi.fn() })).resolves.toBe(false)
    await expect(
      escucharSalirNudo('dev12345', {
        listen: () => {
          throw new Error('y')
        },
        post: vi.fn(),
      }),
    ).resolves.toBe(false)
    expect(aviso).toHaveBeenCalledTimes(2)
    aviso.mockRestore()
  })
  it('si el post de salir falla avisa en consola', async () => {
    const aviso = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    let cb: () => void = () => {}
    const post = vi.fn().mockRejectedValue(new Error('500'))
    await escucharSalirNudo('dev12345', { listen: (_e, f) => (cb = f), post })
    cb()
    await new Promise((r) => setTimeout(r, 0))
    expect(aviso).toHaveBeenCalledTimes(1)
    aviso.mockRestore()
  })
})

describe('atenderOrdenNudo: zonas', () => {
  const zona = { x: 10, y: 20, ancho: 100, alto: 40 }
  it('senalar_zona: invoca nudo_senalar_zona y postea {resultado: ok}', async () => {
    const d = deps(async () => 'ok')
    await atenderOrdenNudo(orden('senalar_zona', { foto: 42, zona, texto: 'Acá' }), 'dev12345', d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_senalar_zona', { foto: 42, zona, texto: 'Acá', sesion: 'A' })
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ resultado: 'ok' })
  })
  it('senalar_zona con foto_vieja postea {error}', async () => {
    const d = deps(async () => {
      throw 'foto_vieja'
    })
    await atenderOrdenNudo(orden('senalar_zona', { foto: 42, zona, texto: 'x' }), 'dev12345', d)
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ error: 'foto_vieja' })
  })
  it('marcar_zonas: invoca nudo_marcar_zonas y postea {resultado: ok}', async () => {
    const zonas = [{ ...zona, etiqueta: 'A' }]
    const d = deps(async () => 'ok')
    await atenderOrdenNudo(orden('marcar_zonas', { foto: 42, zonas }), 'dev12345', d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_marcar_zonas', { foto: 42, zonas, sesion: 'A' })
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ resultado: 'ok' })
  })
  it('marcar_zonas con foto_vieja postea {error}', async () => {
    const d = deps(async () => {
      throw 'foto_vieja'
    })
    await atenderOrdenNudo(orden('marcar_zonas', { foto: 1, zonas: [] }), 'dev12345', d)
    expect((d.post.mock.calls[0][1] as { resultado: unknown }).resultado).toEqual({ error: 'foto_vieja' })
  })
})

describe('atenderOrdenNudo: guia', () => {
  const zona = { x: 10, y: 20, ancho: 100, alto: 40 }
  it('normaliza guia solo si es true', () => {
    expect(normalizarOrdenNudo({ ...base, op: 'estado', args: {}, guia: true })?.guia).toBe(true)
    expect(normalizarOrdenNudo({ ...base, op: 'estado', args: {}, guia: 'si' })?.guia).toBe(false)
    expect(normalizarOrdenNudo({ ...base, op: 'estado', args: {} })?.guia).toBe(false)
  })
  it('con guia suma guia: true en las cuatro operaciones de dibujo', async () => {
    const casos: [OrdenNudo['op'], Record<string, unknown>, string][] = [
      ['senalar', { foto: 1, n: 2, texto: 'x' }, 'nudo_senalar'],
      ['marcar', { foto: 1, marcas: [] }, 'nudo_marcar'],
      ['senalar_zona', { foto: 1, zona, texto: 'x' }, 'nudo_senalar_zona'],
      ['marcar_zonas', { foto: 1, zonas: [] }, 'nudo_marcar_zonas'],
    ]
    for (const [op, args, cmd] of casos) {
      const d = deps(async () => 'ok')
      await atenderOrdenNudo(orden(op, args, true), 'dev12345', d)
      expect(d.invoke).toHaveBeenCalledWith(cmd, expect.objectContaining({ guia: true }))
    }
  })
  it('sin guia los argumentos no llevan la clave', async () => {
    const d = deps(async () => 'ok')
    await atenderOrdenNudo(orden('senalar_zona', { foto: 1, zona, texto: 'x' }), 'dev12345', d)
    expect(Object.keys(d.invoke.mock.calls[0][1] as object)).not.toContain('guia')
  })
  it('controles nunca lleva guia', async () => {
    const d = deps(async () => [])
    await atenderOrdenNudo(orden('controles', {}, true), 'dev12345', d)
    expect(d.invoke).toHaveBeenCalledWith('nudo_controles', undefined)
  })
})
