import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type Api, type TerminalPreview } from '../api/types'

const h = vi.hoisted(() => {
  const listeners: Record<string, Array<() => void>> = {}
  const store = new Map<string, string>()
  const doc = {
    visibilityState: 'visible',
    hidden: false,
    documentElement: { dataset: {}, toggleAttribute() {}, setAttribute() {} },
    createElement: () => ({ style: {}, setAttribute() {}, classList: { add() {} } }),
    createElementNS: () => ({}),
    querySelector: () => null,
    addEventListener: (n: string, f: () => void) => void (listeners[n] ??= []).push(f),
    removeEventListener() {},
  }
  vi.stubGlobal('document', doc)
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener: (n: string, f: () => void) => void (listeners[n] ??= []).push(f),
  })
  vi.stubGlobal('location', { search: '', pathname: '/' })
  vi.stubGlobal('localStorage', {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => void store.set(k, v),
    removeItem: (k: string) => void store.delete(k),
  })
  return { listeners, store, doc }
})

const { init } = await import('./app')
const { act, confirmAccion, dismissAccion, enviados, openAccion } = await import('./terminalActions')
const { clearHistorial, closeVentana, countdown, guardVentana, historial, openVentana, pinProblem, rememberCommand, ventana, ventanaAbierta } = await import('./terminalWrite')
const { addHistorial, validarComando, verInvisibles } = await import('../lib/terminales')

const preview = (over: Partial<TerminalPreview> = {}): TerminalPreview => ({
  huella: 'h1', pane_id: 'w1:p5', workspace: 'Uno', tab: '1', titulo: 'bash', cwd: '/tmp', proceso: 'bash', estado: 'prompt', protegida: false, puede_escribir: true, cierra: 'terminal', ...over,
})

function api(over: Partial<Api> = {}) {
  const fns = {
    previewTerminal: vi.fn().mockResolvedValue(preview()),
    abrirVentana: vi.fn().mockResolvedValue({ token: 'tok-secreto', vence_en: 300, inactividad: 120 }),
    cerrarVentana: vi.fn().mockResolvedValue(undefined),
    enviarComando: vi.fn().mockResolvedValue(undefined),
    getTerminalAuditoria: vi.fn().mockResolvedValue([]),
    ...over,
  }
  init(fns as unknown as Api)
  return fns
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-11-01T12:00:00Z'))
  h.store.clear()
  dismissAccion()
  closeVentana()
  clearHistorial()
})
afterEach(() => {
  closeVentana()
  vi.useRealTimers()
})

describe('validación del comando', () => {
  it.each([
    ['', 'Escribí un comando'],
    ['ls\n', 'caracteres no permitidos'],
    ['ls\tx', 'caracteres no permitidos'],
    ['ls‮x', 'caracteres no permitidos'],
    ['ls x', 'caracteres no permitidos'],
    [' ls', 'Sin espacios'],
    ['ls ', 'Sin espacios'],
    ['-rf /', 'No puede empezar con -'],
    ['x'.repeat(501), 'Máximo 500'],
    ['rm\u00a0-rf', 'caracteres no permitidos'],
    ['ls\u3000x', 'caracteres no permitidos'],
    ['a\u2028b', 'caracteres no permitidos'],
    ['a\u2029b', 'caracteres no permitidos'],
    ['a\u200bb', 'caracteres no permitidos'],
    ['a\u3164b', 'caracteres no permitidos'],
    ['a\u2800b', 'caracteres no permitidos'],
    ['a\ue000b', 'caracteres no permitidos'],
    ['a\ud800b', 'caracteres no permitidos'],
    ['a\u{e0041}b', 'caracteres no permitidos'],
    ['a\x1bb', 'caracteres no permitidos'],
    ['a\x9bb', 'caracteres no permitidos'],
  ])('rechaza %j', (cmd, msg) => {
    expect(validarComando(cmd)).toContain(msg)
  })

  it('acepta un comando normal y el límite exacto', () => {
    expect(validarComando('git status')).toBeNull()
    expect(validarComando('x'.repeat(500))).toBeNull()
  })

  it('muestra los invisibles como código visible', () => {
    expect(verInvisibles('ls‮-la')).toBe('ls⟨U+202E⟩-la')
    expect(verInvisibles('a\nb')).toBe('a⟨U+000A⟩b')
  })
})

describe('historial', () => {
  it('lo más nuevo primero, sin repetidos y con tope de 30', () => {
    let l: string[] = []
    for (let i = 0; i < 40; i++) l = addHistorial(l, `cmd ${i}`)
    expect(l).toHaveLength(30)
    expect(l[0]).toBe('cmd 39')
    expect(addHistorial(l, 'cmd 20')[0]).toBe('cmd 20')
    expect(addHistorial(l, 'cmd 20').filter((c) => c === 'cmd 20')).toHaveLength(1)
  })

  it.each(['export TOKEN=abc', 'curl -H "Authorization: x" u', 'mysql --password=x', 'git clone https://u:p@h/r', 'echo AKIAABCDEFGHIJKLMNOP', 'x ghp_abc'])('no guarda %j', (cmd) => {
    expect(addHistorial(['ls'], cmd)).toEqual(['ls'])
  })

  it('persiste en localStorage y se puede borrar', () => {
    rememberCommand('ls -la')
    expect(JSON.parse(h.store.get('orq.terminales.historial')!)).toEqual(['ls -la'])
    expect(historial.value).toEqual(['ls -la'])
    clearHistorial()
    expect(historial.value).toEqual([])
    expect(h.store.has('orq.terminales.historial')).toBe(false)
  })

  it('sin almacenamiento sigue funcionando en memoria', () => {
    const ls = globalThis.localStorage
    vi.stubGlobal('localStorage', { getItem() { throw new Error('x') }, setItem() { throw new Error('x') }, removeItem() { throw new Error('x') } })
    expect(() => rememberCommand('pwd')).not.toThrow()
    expect(historial.value).toContain('pwd')
    expect(() => clearHistorial()).not.toThrow()
    vi.stubGlobal('localStorage', ls)
  })
})

describe('ventana de escritura', () => {
  it('el token vive solo en memoria', async () => {
    api()
    await openVentana('12345678')
    expect(ventanaAbierta.value).toBe(true)
    expect(ventana.token).toBe('tok-secreto')
    expect([...h.store.values()].join('')).not.toContain('tok-secreto')
    expect(JSON.stringify([...h.store.entries()])).not.toContain('12345678')
  })

  it('la cuenta regresiva baja y al llegar a cero se cierra sola', async () => {
    api()
    await openVentana('12345678')
    expect(countdown.value).toBe(120)
    vi.advanceTimersByTime(30_000)
    expect(countdown.value).toBe(90)
    vi.advanceTimersByTime(95_000)
    expect(ventanaAbierta.value).toBe(false)
    expect(ventana.token).toBe('')
  })

  it('cerrar avisa al servidor con el token y borra el local', async () => {
    const f = api()
    await openVentana('12345678')
    closeVentana()
    expect(f.cerrarVentana).toHaveBeenCalledWith('tok-secreto', false)
    expect(ventana.token).toBe('')
  })

  it('al ocultarse la pantalla o salir de la página cierra con keepalive', async () => {
    const f = api()
    guardVentana()
    await openVentana('12345678')
    h.doc.visibilityState = 'hidden'
    h.listeners.visibilitychange.forEach((fn) => fn())
    expect(f.cerrarVentana).toHaveBeenCalledWith('tok-secreto', true)
    h.doc.visibilityState = 'visible'
    await openVentana('12345678')
    h.listeners.pagehide.forEach((fn) => fn())
    expect(f.cerrarVentana).toHaveBeenCalledTimes(2)
    expect(f.cerrarVentana).toHaveBeenLastCalledWith('tok-secreto', true)
  })

  it('traduce los problemas del PIN', () => {
    expect(pinProblem(new ApiError(401, 'x')).message).toBe('PIN incorrecto')
    expect(pinProblem(new ApiError(429, 'x', 120)).retryAfter).toBe(120)
    expect(pinProblem(new ApiError(403, 'x')).message).toContain('apagada')
    expect(pinProblem(new Error('boom')).message).toBe('No pude conectar con el servidor')
  })
})

describe('enviar un comando', () => {
  it('pide confirmación, manda el token por separado y renueva solo la inactividad', async () => {
    const f = api()
    await openVentana('12345678')
    vi.advanceTimersByTime(100_000)
    await openAccion('comando', 'w1:p5', 'ls -la')
    expect(act.phase).toBe('ready')
    expect(f.enviarComando).not.toHaveBeenCalled()
    const before = enviados.value
    await confirmAccion()
    expect(f.enviarComando).toHaveBeenCalledWith({ id: expect.any(String), pane_id: 'w1:p5', huella: 'h1', comando: 'ls -la' }, 'tok-secreto')
    expect(enviados.value).toBe(before + 1)
    expect(countdown.value).toBe(120)
    expect(historial.value[0]).toBe('ls -la')
    vi.advanceTimersByTime(1200)
    expect(act.kind).toBeNull()
  })

  it('un comando rápido manda el índice y el texto confirmado, para que el servidor los compare', async () => {
    const f = api()
    await openVentana('12345678')
    await openAccion('comando', 'w1:p5', 'git status', 2)
    await confirmAccion()
    expect(f.enviarComando).toHaveBeenCalledWith({ id: expect.any(String), pane_id: 'w1:p5', huella: 'h1', rapido: 2, comando: 'git status' }, 'tok-secreto')
  })

  it('no ofrece comando si hay un programa corriendo', async () => {
    const f = api({ previewTerminal: vi.fn().mockResolvedValue(preview({ estado: 'corriendo', proceso: 'vim' })) })
    await openAccion('comando', 'w1:p5', 'ls')
    expect(act.phase).toBe('error')
    expect(f.enviarComando).not.toHaveBeenCalled()
  })

  it('un 401 olvida la ventana y pide abrirla de nuevo', async () => {
    api({ enviarComando: vi.fn().mockRejectedValue(new ApiError(401, 'abrí la escritura')) })
    await openVentana('12345678')
    await openAccion('comando', 'w1:p5', 'ls')
    await confirmAccion()
    expect(act.phase).toBe('error')
    expect(act.error).toContain('Abrila de nuevo')
    expect(ventanaAbierta.value).toBe(false)
    expect(historial.value).not.toContain('ls')
  })
})
