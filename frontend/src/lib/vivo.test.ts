import { describe, expect, it, vi } from 'vitest'
import {
  ConexionVivo,
  MSG_NO_CONECTE,
  parseMensajeVivo,
  urlVivo,
  type WebSocketLike,
} from './vivo'

describe('urlVivo', () => {
  it('usa ws en http y escapa el pane id', () => {
    expect(urlVivo('g1:p2', { protocol: 'http:', host: 'localhost:5173' })).toBe(
      'ws://localhost:5173/api/terminal/g1%3Ap2/vivo',
    )
  })
  it('usa wss en https', () => {
    expect(urlVivo('g1:p1', { protocol: 'https:', host: 'colmena.test' })).toBe(
      'wss://colmena.test/api/terminal/g1%3Ap1/vivo',
    )
  })
})

describe('parseMensajeVivo', () => {
  it('acepta mensajes válidos', () => {
    expect(parseMensajeVivo({ tipo: 'foto', columnas: 80, filas: 24, texto: 'hola' })).toEqual({
      tipo: 'foto',
      columnas: 80,
      filas: 24,
      texto: 'hola',
    })
    expect(parseMensajeVivo({ tipo: 'salida', texto: 'x' })).toEqual({ tipo: 'salida', texto: 'x' })
    expect(parseMensajeVivo({ tipo: 'termino', codigo: 0 })).toEqual({ tipo: 'termino', codigo: 0 })
    expect(parseMensajeVivo({ tipo: 'termino', codigo: null })).toEqual({ tipo: 'termino', codigo: null })
    expect(parseMensajeVivo({ tipo: 'cerrada' })).toEqual({ tipo: 'cerrada' })
    expect(parseMensajeVivo({ tipo: 'error', codigo: 'cupo', mensaje: 'lleno' })).toEqual({
      tipo: 'error',
      codigo: 'cupo',
      mensaje: 'lleno',
    })
  })

  it('descarta inválidos', () => {
    expect(parseMensajeVivo(null)).toBeNull()
    expect(parseMensajeVivo({ tipo: 'foto', columnas: 0, filas: 24, texto: 'a' })).toBeNull()
    expect(parseMensajeVivo({ tipo: 'foto', columnas: 80, filas: 2000, texto: 'a' })).toBeNull()
    expect(parseMensajeVivo({ tipo: 'salida', texto: 1 })).toBeNull()
    expect(parseMensajeVivo({ tipo: 'error', codigo: 'otro', mensaje: 'x' })).toBeNull()
    expect(parseMensajeVivo({ tipo: 'desconocido' })).toBeNull()
  })
})

class FakeSocket implements WebSocketLike {
  static all: FakeSocket[] = []
  onopen: ((ev: Event) => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  onclose: ((ev: { code: number }) => void) | null = null
  onerror: ((ev: Event) => void) | null = null
  send = vi.fn()
  closed = false

  constructor(readonly url: string) {
    FakeSocket.all.push(this)
  }

  close(): void {
    this.closed = true
  }

  msg(data: unknown): void {
    this.onmessage?.({ data: JSON.stringify(data) })
  }

  drop(code = 1006): void {
    this.onclose?.({ code })
  }
}

function setup() {
  FakeSocket.all = []
  const timers = new Map<number, { fn: () => void; ms: number }>()
  let seq = 0
  const deps = {
    crearSocket: (url: string) => new FakeSocket(url),
    setTimeout: (fn: () => void, ms: number) => {
      const id = ++seq
      timers.set(id, { fn, ms })
      return id
    },
    clearTimeout: (id: number) => {
      timers.delete(id)
    },
  }
  const flush = () => {
    const [id, t] = [...timers.entries()][0] ?? []
    if (id === undefined || !t) return
    timers.delete(id)
    t.fn()
  }
  return { deps, flush, timers }
}

describe('ConexionVivo', () => {
  it('foto dispara onFoto y en_vivo; salida escribe', () => {
    const { deps } = setup()
    const fotos: unknown[] = []
    const salidas: string[] = []
    const estados: string[] = []
    const c = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: (f) => fotos.push(f),
      onSalida: (t) => salidas.push(t),
      onEstado: (e) => estados.push(e),
    })
    c.abrir()
    const ws = FakeSocket.all[0]!
    ws.msg({ tipo: 'foto', columnas: 10, filas: 5, texto: 'init' })
    ws.msg({ tipo: 'salida', texto: 'more' })
    expect(fotos).toHaveLength(1)
    expect(salidas).toEqual(['more'])
    expect(estados).toContain('en_vivo')
    expect(ws.send).not.toHaveBeenCalled()
    c.cerrar()
  })

  it('termino y cerrada son finales sin reconectar', () => {
    const { deps, flush } = setup()
    const estados: string[] = []
    const c = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: () => {},
      onSalida: () => {},
      onEstado: (e) => estados.push(e),
    })
    c.abrir()
    FakeSocket.all[0]!.msg({ tipo: 'termino', codigo: 42 })
    c.abrir()
    flush()
    expect(estados.at(-1)).toBe('terminada')
    expect(FakeSocket.all).toHaveLength(1)

    const c2 = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: () => {},
      onSalida: () => {},
      onEstado: (e) => estados.push(e),
    })
    c2.abrir()
    FakeSocket.all[1]!.msg({ tipo: 'cerrada' })
    c2.abrir()
    flush()
    expect(estados.at(-1)).toBe('cerrada')
    expect(FakeSocket.all).toHaveLength(2)
  })

  it('caido reconecta con espera creciente', () => {
    const { deps, flush, timers } = setup()
    const estados: string[] = []
    const c = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: () => {},
      onSalida: () => {},
      onEstado: (e) => estados.push(e),
    })
    c.abrir()
    const ws = FakeSocket.all[0]!
    ws.msg({ tipo: 'caido' })
    ws.drop(4503)
    expect(estados).toContain('caido')
    expect(timers.size).toBe(1)
    const wait1 = [...timers.values()][0]!.ms
    flush()
    expect(FakeSocket.all).toHaveLength(2)
    FakeSocket.all[1]!.msg({ tipo: 'caido' })
    FakeSocket.all[1]!.drop(4503)
    const wait2 = [...timers.values()][0]!.ms
    expect(wait2).toBeGreaterThan(wait1)
    c.cerrar()
  })

  it('desfasado reconecta enseguida', () => {
    const { deps, flush, timers } = setup()
    const c = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: () => {},
      onSalida: () => {},
      onEstado: () => {},
    })
    c.abrir()
    FakeSocket.all[0]!.msg({ tipo: 'foto', columnas: 4, filas: 4, texto: '' })
    FakeSocket.all[0]!.msg({ tipo: 'desfasado' })
    FakeSocket.all[0]!.drop(4409)
    expect([...timers.values()][0]?.ms).toBe(0)
    flush()
    expect(FakeSocket.all).toHaveLength(2)
    c.cerrar()
  })

  it('error apagado y no_existe son finales', () => {
    const { deps } = setup()
    for (const codigo of ['apagado', 'no_existe'] as const) {
      const estados: string[] = []
      const c = new ConexionVivo({
        paneId: 'g1:p1',
        loc: { protocol: 'http:', host: 'h' },
        deps,
        onFoto: () => {},
        onSalida: () => {},
        onEstado: (e) => estados.push(e),
      })
      c.abrir()
      const n = FakeSocket.all.length
      FakeSocket.all[n - 1]!.msg({ tipo: 'error', codigo, mensaje: 'x' })
      c.abrir()
      expect(FakeSocket.all).toHaveLength(n)
      expect(estados).toContain('error')
      c.cerrar()
    }
  })

  it('dos cierres sin mensajes → error con texto de sesión', () => {
    const { deps, flush } = setup()
    let msg = ''
    const c = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: () => {},
      onSalida: () => {},
      onEstado: (e, m) => {
        if (e === 'error') msg = m ?? ''
      },
    })
    c.abrir()
    FakeSocket.all[0]!.drop(1006)
    flush()
    FakeSocket.all[1]!.drop(1008)
    expect(msg).toBe(MSG_NO_CONECTE)
    c.cerrar()
  })

  it('cierre inesperado tras foto reconecta con backoff', () => {
    const { deps, flush, timers } = setup()
    const estados: string[] = []
    const c = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: () => {},
      onSalida: () => {},
      onEstado: (e) => estados.push(e),
    })
    c.abrir()
    FakeSocket.all[0]!.msg({ tipo: 'foto', columnas: 8, filas: 4, texto: 'a' })
    FakeSocket.all[0]!.drop(1006)
    expect(estados).toContain('reconectando')
    expect([...timers.values()][0]?.ms).toBe(500)
    flush()
    expect(FakeSocket.all).toHaveLength(2)
    c.cerrar()
  })

  it('cerrar cancela timers y no reconecta', () => {
    const { deps, flush, timers } = setup()
    const c = new ConexionVivo({
      paneId: 'g1:p1',
      loc: { protocol: 'http:', host: 'h' },
      deps,
      onFoto: () => {},
      onSalida: () => {},
      onEstado: () => {},
    })
    c.abrir()
    FakeSocket.all[0]!.msg({ tipo: 'foto', columnas: 8, filas: 4, texto: 'a' })
    FakeSocket.all[0]!.drop(1006)
    c.cerrar()
    expect(timers.size).toBe(0)
    flush()
    expect(FakeSocket.all).toHaveLength(1)
  })
})

describe('textos visibles sin palabra prohibida', () => {
  it('vivo.ts no contiene la palabra en textos de usuario', () => {
    const src = [
      MSG_NO_CONECTE,
      'Tu sesión de Colmena venció. Volvé a entrar.',
      'Conectando…',
      'En vivo',
      'Reconectando…',
    ].join(' ')
    expect(src.toLowerCase()).not.toMatch(/\bflujo\b/)
  })
})
