import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  anotarInvokeFallido,
  crearReporteConexion,
  anotarNotch,
  enviarPendientes,
  INTERVALO_MS,
  iniciarRegistroNotch,
  LOTES_POR_CICLO,
  mensajeDeError,
  TRAS_ERROR_MS,
} from './registroPuente'

class EventoError {
  constructor(public type: string, public init: { message?: string; filename?: string; lineno?: number; reason?: unknown; error?: unknown }) {}
  get message() { return this.init.message }
  get filename() { return this.init.filename }
  get lineno() { return this.init.lineno }
  get reason() { return this.init.reason }
  get error() { return this.init.error }
}

function ventana(invoke: (c: string, a?: Record<string, unknown>) => Promise<unknown>) {
  const oyentes: Record<string, Array<(e: unknown) => void>> = {}
  const tauri: Record<string, unknown> = { core: { invoke } }
  const listen = vi.fn(async (_ev: string, _cb: (e: unknown) => void) => () => undefined)
  tauri.event = { listen }
  const w = {
    __TAURI__: tauri,
    addEventListener: (t: string, cb: (e: unknown) => void) => { (oyentes[t] ??= []).push(cb) },
    removeEventListener: (t: string, cb: (e: unknown) => void) => { oyentes[t] = (oyentes[t] ?? []).filter((x) => x !== cb) },
    dispatch: (t: string, e: unknown) => (oyentes[t] ?? []).forEach((cb) => cb(e)),
  }
  return { w: w as unknown as Window & { dispatch: (t: string, e: unknown) => void }, listen }
}

const llamadas = (invoke: ReturnType<typeof vi.fn>, cmd: string) => invoke.mock.calls.filter((c) => c[0] === cmd)

beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('ErrorEvent', EventoError)
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

describe('enviarPendientes', () => {
  it('manda el lote y lo confirma', async () => {
    const invoke = vi.fn(async (c: string) => (c === 'registro_pendiente' ? (invoke.mock.calls.length < 3 ? { lote: 4, lineas: ['l'] } : null) : undefined))
    const post = vi.fn().mockResolvedValue(undefined)
    expect(await enviarPendientes({ invoke, post })).toBe('enviado')
    expect(post).toHaveBeenCalledWith('/api/registro/app', { lineas: ['l'] })
    expect(invoke).toHaveBeenCalledWith('registro_enviado', { lote: 4 })
  })

  it('enviarPendientes manda lineas y eventos en un solo POST', async () => {
    const ev = { ts: '2026-11-25T10:00:00', origen: 'app', evento: 'arranque', ok: true, codigo: null, ms: null, version: '1.0.0' }
    const invoke = vi.fn(async (c: string) => (c === 'registro_pendiente' ? (invoke.mock.calls.length < 3 ? { lote: 4, lineas: ['l'], eventos: [ev] } : null) : undefined))
    const post = vi.fn().mockResolvedValue(undefined)
    expect(await enviarPendientes({ invoke, post })).toBe('enviado')
    expect(post).toHaveBeenCalledWith('/api/registro/app', { lineas: ['l'], eventos: [ev] })
    expect(invoke).toHaveBeenCalledWith('registro_enviado', { lote: 4 })
  })

  it('un lote solo de eventos no manda la clave lineas, y uno viejo sin eventos no manda eventos', async () => {
    const ev = { ts: 't', origen: 'app', evento: 'x', ok: true }
    for (const [lote, cuerpo] of [
      [{ lote: 1, lineas: [], eventos: [ev] }, { eventos: [ev] }],
      [{ lote: 1, lineas: ['l'] }, { lineas: ['l'] }],
    ] as const) {
      const invoke = vi.fn(async (c: string) => (c === 'registro_pendiente' ? (invoke.mock.calls.length < 3 ? lote : null) : undefined))
      const post = vi.fn().mockResolvedValue(undefined)
      await enviarPendientes({ invoke, post })
      expect(post).toHaveBeenCalledWith('/api/registro/app', cuerpo)
    }
  })

  it('sin pendientes devuelve vacio y no postea', async () => {
    const invoke = vi.fn().mockResolvedValue(null)
    const post = vi.fn()
    expect(await enviarPendientes({ invoke, post })).toBe('vacio')
    expect(post).not.toHaveBeenCalled()
  })

  it('si el post falla no confirma', async () => {
    const invoke = vi.fn().mockResolvedValue({ lote: 1, lineas: ['l'] })
    const post = vi.fn().mockRejectedValue(new Error('500'))
    expect(await enviarPendientes({ invoke, post })).toBe('fallo')
    expect(llamadas(invoke, 'registro_enviado')).toHaveLength(0)
  })

  it('corta en LOTES_POR_CICLO lotes', async () => {
    const invoke = vi.fn().mockResolvedValue({ lote: 1, lineas: ['l'] })
    const post = vi.fn().mockResolvedValue(undefined)
    expect(await enviarPendientes({ invoke, post })).toBe('enviado')
    expect(post).toHaveBeenCalledTimes(LOTES_POR_CICLO)
  })
})

describe('anotarNotch', () => {
  it('fuera del programa no hace nada', () => {
    expect(() => anotarNotch('error', 'x', {} as Window)).not.toThrow()
  })

  it('invoca registro_anotar y traga el error', async () => {
    const invoke = vi.fn().mockRejectedValue(new Error('x'))
    const { w } = ventana(invoke)
    expect(() => anotarNotch('aviso', 'hola', w)).not.toThrow()
    expect(invoke).toHaveBeenCalledWith('registro_anotar', { nivel: 'aviso', mensaje: 'hola' })
    await vi.advanceTimersByTimeAsync(0)
  })

  it('traga también un invoke que lanza síncrono', () => {
    const invoke = vi.fn(() => { throw new Error('x') })
    const { w } = ventana(invoke as never)
    expect(() => anotarNotch('info', 'hola', w)).not.toThrow()
  })
})

describe('anotarInvokeFallido', () => {
  it('manda invoke_<comando> como código', () => {
    const invoke = vi.fn(async () => undefined)
    const { w } = ventana(invoke)
    anotarInvokeFallido('reunion_estado', w)
    expect(invoke).toHaveBeenCalledWith('registro_evento', { origen: 'notch', evento: 'error', ok: false, codigo: 'invoke_reunion_estado' })
  })
  it('un comando raro o largo queda como otro', () => {
    const invoke = vi.fn(async () => undefined)
    const { w } = ventana(invoke)
    anotarInvokeFallido('Mi Comando!', w)
    anotarInvokeFallido('c'.repeat(40), w)
    expect(invoke).toHaveBeenNthCalledWith(1, 'registro_evento', expect.objectContaining({ codigo: 'otro' }))
    expect(invoke).toHaveBeenNthCalledWith(2, 'registro_evento', expect.objectContaining({ codigo: 'otro' }))
  })
  it('fuera del programa no hace nada', () => {
    expect(() => anotarInvokeFallido('x', {} as Window)).not.toThrow()
  })
})

describe('crearReporteConexion', () => {
  const eventos = (invoke: ReturnType<typeof vi.fn>) => llamadas(invoke, 'registro_evento').map((c) => c[1])

  it('emite solo en la transición, empezando sin estado', () => {
    const invoke = vi.fn(async () => undefined)
    const { w } = ventana(invoke)
    const reportar = crearReporteConexion(w)
    reportar(true)
    reportar(true)
    reportar(false)
    reportar(false)
    reportar(true)
    expect(eventos(invoke)).toEqual([
      { origen: 'notch', evento: 'conectado', ok: true },
      { origen: 'notch', evento: 'desconectado', ok: false, codigo: 'red' },
      { origen: 'notch', evento: 'conectado', ok: true },
    ])
  })

  it('si la primera noticia es la caída, emite desconectado', () => {
    const invoke = vi.fn(async () => undefined)
    const { w } = ventana(invoke)
    crearReporteConexion(w)(false)
    expect(eventos(invoke)).toEqual([{ origen: 'notch', evento: 'desconectado', ok: false, codigo: 'red' }])
  })

  it('fuera del programa no hace nada', () => {
    expect(() => crearReporteConexion({} as Window)(true)).not.toThrow()
  })
})

describe('mensajeDeError', () => {
  it('deja solo el nombre base del archivo', () => {
    const e = new ErrorEvent('error', { message: 'x is undefined', filename: 'http://h:8770/assets/a-1.js?v=2#z', lineno: 9 })
    expect(mensajeDeError(e)).toBe('x is undefined (a-1.js:9)')
  })
  it('Error devuelve name: message', () => {
    expect(mensajeDeError(new TypeError('boom'))).toBe('TypeError: boom')
  })
  it('ErrorEvent con error Error usa la regla de Error', () => {
    const f = 'http://h/a.js'
    expect(mensajeDeError(new ErrorEvent('error', { message: 'Uncaught TypeError: x', filename: f, lineno: 1, error: new TypeError('boom') }))).toBe('TypeError: boom (a.js:1)')
    expect(mensajeDeError(new ErrorEvent('error', { message: 'Uncaught SyntaxError: "secreto" is not valid JSON', filename: f, lineno: 2, error: new SyntaxError('"secreto"') }))).toBe('SyntaxError (a.js:2)')
  })
  it('ErrorEvent con error que no es Error devuelve su tipo', () => {
    expect(mensajeDeError(new ErrorEvent('error', { message: 'Uncaught texto', filename: 'http://h/a.js', lineno: 3, error: 'texto' }))).toBe('rechazo: string (a.js:3)')
  })
  it('ErrorEvent sin error y con SyntaxError en el mensaje devuelve solo SyntaxError', () => {
    expect(mensajeDeError(new ErrorEvent('error', { message: 'Uncaught SyntaxError: "secreto" is not valid JSON', filename: 'http://h/a.js', lineno: 4 }))).toBe('SyntaxError (a.js:4)')
  })
  it('SyntaxError devuelve solo el nombre, sin el fragmento del texto', () => {
    let e: unknown
    try { JSON.parse('{"secreto": oops') } catch (x) { e = x }
    expect(mensajeDeError(e)).toBe('SyntaxError')
  })
  it('otro valor devuelve solo su tipo', () => {
    expect(mensajeDeError('texto del usuario')).toBe('rechazo: string')
    expect(mensajeDeError({ a: 1 })).toBe('rechazo: object')
    expect(mensajeDeError(42)).toBe('rechazo: number')
  })
  it('recorta a 300', () => {
    expect(mensajeDeError(new Error('a'.repeat(500)))).toHaveLength(300)
  })
})

describe('iniciarRegistroNotch', () => {
  it('error de ventana anota y envía a los 2 s', async () => {
    const invoke = vi.fn(async () => null)
    const { w } = ventana(invoke)
    const post = vi.fn()
    const parar = iniciarRegistroNotch({ w, post })
    w.dispatch('error', new ErrorEvent('error', { message: 'rota', filename: 'http://h/a.js', lineno: 3 }))
    expect(invoke).toHaveBeenCalledWith('registro_anotar', { nivel: 'error', mensaje: 'rota (a.js:3)' })
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(TRAS_ERROR_MS)
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(1)
    parar()
  })

  it('un error del notch se anota como evento con código', () => {
    const invoke = vi.fn(async () => null)
    const { w } = ventana(invoke)
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    w.dispatch('error', new ErrorEvent('error', { message: 'secreto-77', filename: 'http://h/a.js', lineno: 3 }))
    expect(invoke).toHaveBeenCalledWith('registro_evento', { origen: 'notch', evento: 'error', ok: false, codigo: 'onerror' })
    expect(JSON.stringify(llamadas(invoke, 'registro_evento'))).not.toContain('secreto')
    parar()
  })

  it('un rechazo sin atrapar se anota como evento promesa', () => {
    const invoke = vi.fn(async () => null)
    const { w } = ventana(invoke)
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    w.dispatch('unhandledrejection', { reason: new RangeError('secreto-88') })
    expect(invoke).toHaveBeenCalledWith('registro_evento', { origen: 'notch', evento: 'error', ok: false, codigo: 'promesa' })
    expect(JSON.stringify(llamadas(invoke, 'registro_evento'))).not.toContain('secreto')
    parar()
  })

  it('envía cada 30 s y el detener lo corta', async () => {
    const invoke = vi.fn(async () => null)
    const { w } = ventana(invoke)
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    await vi.advanceTimersByTimeAsync(INTERVALO_MS)
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(1)
    await vi.advanceTimersByTimeAsync(INTERVALO_MS)
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(2)
    parar()
    await vi.advanceTimersByTimeAsync(INTERVALO_MS * 3)
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(2)
  })

  it('unhandledrejection anota error', () => {
    const invoke = vi.fn(async () => null)
    const { w } = ventana(invoke)
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    w.dispatch('unhandledrejection', { reason: new RangeError('mala') })
    expect(invoke).toHaveBeenCalledWith('registro_anotar', { nivel: 'error', mensaje: 'RangeError: mala' })
    parar()
  })

  it('el evento registro-hay programa un envío', async () => {
    const invoke = vi.fn(async () => null)
    const { w, listen } = ventana(invoke)
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    expect(listen).toHaveBeenCalledWith('registro-hay', expect.any(Function))
    listen.mock.calls[0][1]({})
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(0)
    await vi.advanceTimersByTimeAsync(TRAS_ERROR_MS)
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(1)
    parar()
  })

  it('si listen lanza o no devuelve promesa, no lanza', () => {
    for (const listen of [() => { throw new Error('x') }, () => undefined]) {
      const w = { addEventListener() {}, removeEventListener() {}, __TAURI__: { core: { invoke: vi.fn() }, event: { listen } } } as unknown as Window
      expect(() => iniciarRegistroNotch({ w, post: vi.fn() })()).not.toThrow()
    }
  })

  it('el ciclo de 30 s sigue activo si listen lanza', async () => {
    const invoke = vi.fn(async () => null)
    const { w } = ventana(invoke)
    ;(w.__TAURI__!.event as { listen: unknown }).listen = () => { throw new Error('x') }
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    await vi.advanceTimersByTimeAsync(INTERVALO_MS)
    expect(llamadas(invoke, 'registro_pendiente')).toHaveLength(1)
    parar()
  })

  it('fuera del programa devuelve un detener que no hace nada', () => {
    const w = { addEventListener: vi.fn() } as unknown as Window
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    expect(() => parar()).not.toThrow()
    expect(w.addEventListener).not.toHaveBeenCalled()
  })

  it('no solapa ciclos: un envío en curso ignora el siguiente disparo', async () => {
    let soltar: (v: unknown) => void = () => {}
    const invoke = vi.fn(() => new Promise((r) => { soltar = r }))
    const { w } = ventana(invoke as never)
    const parar = iniciarRegistroNotch({ w, post: vi.fn() })
    await vi.advanceTimersByTimeAsync(INTERVALO_MS)
    await vi.advanceTimersByTimeAsync(INTERVALO_MS)
    expect(llamadas(invoke as never, 'registro_pendiente')).toHaveLength(1)
    soltar(null)
    parar()
  })
})
