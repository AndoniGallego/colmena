import { describe, expect, it, vi } from 'vitest'
import { ColaTexto, conectarLector, normalizarLector, normalizarTextoLector, TEXTO_POST_MAX } from './reunionPuente'

describe('ColaTexto', () => {
  it('acota a 20 000 descartando lo más viejo y anteponiendo […]', () => {
    const c = new ColaTexto()
    c.agregar('a'.repeat(15_000))
    c.agregar('b'.repeat(15_000))
    expect(c.largo).toBeLessThanOrEqual(20_000)
    const t = c.tomar()!
    expect(t.startsWith('[…] ')).toBe(true)
  })
  it('un máximo chico también acota', () => {
    const c = new ColaTexto(50)
    c.agregar('x'.repeat(200))
    expect(c.largo).toBeLessThanOrEqual(50)
  })
  it('tomar devuelve como mucho 2000 caracteres y deja el resto', () => {
    const c = new ColaTexto()
    c.agregar('palabra '.repeat(900))
    const t = c.tomar()!
    expect(t.length).toBeLessThanOrEqual(TEXTO_POST_MAX)
    expect(c.largo).toBeGreaterThan(0)
  })
  it('tomar en una cola vacía da null', () => {
    expect(new ColaTexto().tomar()).toBeNull()
  })
  it('devolver reencola adelante', () => {
    const c = new ColaTexto()
    c.agregar('segundo')
    c.devolver('primero')
    expect(c.tomar()).toBe('primero segundo')
  })
})

describe('normalizarLector', () => {
  it('acepta estados conocidos y el motivo', () => {
    expect(normalizarLector({ estado: 'escuchando', motivo: null })).toEqual({ estado: 'escuchando' })
    expect(normalizarLector({ estado: 'apagado', motivo: 'bandeja' })).toEqual({ estado: 'apagado', motivo: 'bandeja' })
  })
  it('rechaza estados desconocidos y basura', () => {
    expect(normalizarLector({ estado: 'raro' })).toBeNull()
    expect(normalizarLector(null)).toBeNull()
    expect(normalizarLector('escuchando')).toBeNull()
  })
})

describe('normalizarTextoLector', () => {
  it('acepta texto con ts', () => {
    expect(normalizarTextoLector({ texto: 'hola', ts: 5 })).toEqual({ texto: 'hola', ts: 5 })
  })
  it('descarta vacío, solo espacios y de más de 2000', () => {
    expect(normalizarTextoLector({ texto: '', ts: 1 })).toBeNull()
    expect(normalizarTextoLector({ texto: '   ', ts: 1 })).toBeNull()
    expect(normalizarTextoLector({ texto: 'a'.repeat(2001), ts: 1 })).toBeNull()
    expect(normalizarTextoLector({ texto: 1 })).toBeNull()
  })
})

function armar(opts: { post?: (u: string, b: unknown) => Promise<unknown>; reunion?: string | null } = {}) {
  const handlers = new Map<string, (e: { payload: unknown }) => void>()
  const listen = vi.fn(async (nombre: string, cb: (e: { payload: unknown }) => void) => {
    handlers.set(nombre, cb)
    return () => handlers.delete(nombre)
  })
  const post = vi.fn(opts.post ?? (async () => undefined))
  const alLector = vi.fn()
  const invoke = vi.fn(async () => 'apagado')
  const reunionId = vi.fn(() => (opts.reunion === undefined ? 'r1' : opts.reunion))
  const deps = { listen, invoke, post, reunionId, device: 'dev12345', alLector }
  return { handlers, deps, post, alLector, listen, opts }
}
const tick = () => new Promise((r) => setTimeout(r, 0))

describe('conectarLector', () => {
  it('un reunion-texto se postea a /api/reunion/texto', async () => {
    const { handlers, deps, post } = armar()
    await conectarLector(deps)
    handlers.get('reunion-texto')!({ payload: { texto: 'hola', ts: 1 } })
    await tick()
    expect(post).toHaveBeenCalledWith('/api/reunion/texto', { reunion: 'r1', device: 'dev12345', texto: 'hola' })
  })
  it('si el post falla el texto queda y sale en el próximo envío', async () => {
    let falla = true
    const { handlers, deps, post } = armar({
      post: async () => {
        if (falla) throw new Error('503')
      },
    })
    await conectarLector(deps)
    handlers.get('reunion-texto')!({ payload: { texto: 'uno', ts: 1 } })
    await tick()
    falla = false
    handlers.get('reunion-texto')!({ payload: { texto: 'dos', ts: 2 } })
    await tick()
    expect(post).toHaveBeenLastCalledWith('/api/reunion/texto', { reunion: 'r1', device: 'dev12345', texto: 'uno dos' })
  })
  it('sin reunión activa el texto se descarta y no viaja cuando empieza otra', async () => {
    const { handlers, deps, post, opts } = armar({ reunion: null })
    await conectarLector(deps)
    handlers.get('reunion-texto')!({ payload: { texto: 'hola', ts: 1 } })
    await tick()
    expect(post).not.toHaveBeenCalled()
    opts.reunion = 'r2'
    handlers.get('reunion-texto')!({ payload: { texto: 'nuevo', ts: 2 } })
    await tick()
    expect(post).toHaveBeenCalledTimes(1)
    expect(post).toHaveBeenCalledWith('/api/reunion/texto', { reunion: 'r2', device: 'dev12345', texto: 'nuevo' })
  })
  it('al empezar otra reunión no viaja el texto que quedó de la anterior', async () => {
    let falla = true
    const { handlers, deps, post, opts } = armar({
      post: async () => {
        if (falla) throw new Error('503')
      },
    })
    await conectarLector(deps)
    handlers.get('reunion-texto')!({ payload: { texto: 'privado de r1', ts: 1 } })
    await tick()
    falla = false
    opts.reunion = 'r2'
    handlers.get('reunion-texto')!({ payload: { texto: 'de r2', ts: 2 } })
    await tick()
    expect(post).toHaveBeenLastCalledWith('/api/reunion/texto', { reunion: 'r2', device: 'dev12345', texto: 'de r2' })
  })
  it('descartar tira lo que quedó en la cola', async () => {
    let falla = true
    const { handlers, deps, post } = armar({
      post: async () => {
        if (falla) throw new Error('503')
      },
    })
    const h = await conectarLector(deps)
    handlers.get('reunion-texto')!({ payload: { texto: 'viejo', ts: 1 } })
    await tick()
    h.descartar()
    falla = false
    handlers.get('reunion-texto')!({ payload: { texto: 'nuevo', ts: 2 } })
    await tick()
    expect(post).toHaveBeenLastCalledWith('/api/reunion/texto', { reunion: 'r1', device: 'dev12345', texto: 'nuevo' })
  })
  it('un texto inválido no se manda', async () => {
    const { handlers, deps, post } = armar()
    await conectarLector(deps)
    handlers.get('reunion-texto')!({ payload: { texto: '' } })
    await tick()
    expect(post).not.toHaveBeenCalled()
  })
  it('reunion-lector llama a alLector con el motivo', async () => {
    const { handlers, deps, alLector } = armar()
    await conectarLector(deps)
    handlers.get('reunion-lector')!({ payload: { estado: 'apagado', motivo: 'bandeja' } })
    expect(alLector).toHaveBeenCalledWith('apagado', 'bandeja')
  })
  it('vaciar espera los envíos en curso y manda lo que quede', async () => {
    const soltar: Array<() => void> = []
    const { handlers, deps, post } = armar({ post: () => new Promise<void>((r) => soltar.push(r)) })
    const h = await conectarLector(deps)
    handlers.get('reunion-texto')!({ payload: { texto: 'a', ts: 1 } })
    handlers.get('reunion-texto')!({ payload: { texto: 'b', ts: 2 } })
    let listo = false
    const p = h.vaciar().then(() => (listo = true))
    await tick()
    expect(listo).toBe(false)
    soltar.shift()!()
    await tick()
    soltar.shift()?.()
    await p
    expect(post.mock.calls.map((c) => (c[1] as { texto: string }).texto).join(' ')).toBe('a b')
  })
  it('la función devuelta deja de escuchar', async () => {
    const { handlers, deps } = armar()
    const h = await conectarLector(deps)
    h()
    await tick()
    expect(handlers.size).toBe(0)
  })
})
