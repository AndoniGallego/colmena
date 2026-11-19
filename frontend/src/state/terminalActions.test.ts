import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError, type Api, type TerminalPreview } from '../api/types'

vi.hoisted(() => {
  vi.stubGlobal('document', {
    visibilityState: 'visible',
    hidden: false,
    documentElement: { dataset: {}, toggleAttribute() {}, setAttribute() {} },
    createElement: () => ({ style: {}, setAttribute() {}, classList: { add() {} } }),
    createElementNS: () => ({}),
    querySelector: () => null,
    addEventListener() {},
    removeEventListener() {},
  })
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
  vi.stubGlobal('location', { search: '', pathname: '/' })
  vi.stubGlobal('history', { pushState() {}, replaceState() {}, back: vi.fn() })
})

const { init } = await import('./app')
const { act, confirmAccion, dismissAccion, openAccion } = await import('./terminalActions')
const { notaCierre, terminalError } = await import('../lib/terminales')
const { openTerminal, openTerminalId } = await import('./terminales')

const preview = (over: Partial<TerminalPreview> = {}): TerminalPreview => ({
  huella: 'h1', pane_id: 'w1:p5', workspace: 'Uno', tab: '1', titulo: 'bash', cwd: '/tmp', proceso: 'bash', estado: 'prompt', protegida: false, puede_escribir: true, cierra: 'terminal', ...over,
})

function api(over: Partial<Api>) {
  const fns = {
    previewTerminal: vi.fn().mockResolvedValue(preview()),
    terminalCtrlC: vi.fn().mockResolvedValue(undefined),
    repetirPreparar: vi.fn().mockResolvedValue({ linea: 'ls -la', antes: '', huella2: 'h2' }),
    repetirConfirmar: vi.fn().mockResolvedValue(true),
    cerrarTerminal: vi.fn().mockResolvedValue(undefined),
    getTerminalAuditoria: vi.fn().mockResolvedValue([]),
    ...over,
  }
  init(fns as unknown as Api)
  return fns
}

beforeEach(() => dismissAccion())

describe('acciones de terminal', () => {
  it('Ctrl+C: previsualiza, espera confirmación y manda la huella', async () => {
    const f = api({ previewTerminal: vi.fn().mockResolvedValue(preview({ estado: 'corriendo' })) })
    await openAccion('ctrl-c', 'w1:p5')
    expect(act.phase).toBe('ready')
    expect(f.terminalCtrlC).not.toHaveBeenCalled()
    vi.useFakeTimers()
    await confirmAccion()
    expect(f.terminalCtrlC).toHaveBeenCalledWith({ id: expect.any(String), pane_id: 'w1:p5', huella: 'h1' })
    expect(act.listo).toBe(true)
    vi.advanceTimersByTime(1200)
    expect(act.kind).toBeNull()
    vi.useRealTimers()
  })

  it('repetir: muestra la línea y recién ejecuta al confirmar', async () => {
    const f = api({})
    await openAccion('repetir', 'w1:p5')
    expect(act.prep?.linea).toBe('ls -la')
    expect(f.repetirConfirmar).not.toHaveBeenCalled()
    await confirmAccion()
    expect(f.repetirConfirmar).toHaveBeenCalledWith({ id: expect.any(String), pane_id: 'w1:p5', huella2: 'h2', ejecutar: true })
  })

  it('cerrar la hoja con la línea subida manda la cancelación para limpiar el prompt', async () => {
    const f = api({})
    await openAccion('repetir', 'w1:p5')
    dismissAccion()
    expect(f.repetirConfirmar).toHaveBeenCalledWith(expect.objectContaining({ ejecutar: false, huella2: 'h2' }))
  })

  it('no repite si hay un programa corriendo ni si el workspace está protegido', async () => {
    const f = api({ previewTerminal: vi.fn().mockResolvedValue(preview({ estado: 'corriendo', proceso: 'vim' })) })
    await openAccion('repetir', 'w1:p5')
    expect(act.phase).toBe('error')
    expect(act.error).toContain('vim')
    expect(f.repetirPreparar).not.toHaveBeenCalled()
    api({ previewTerminal: vi.fn().mockResolvedValue(preview({ protegida: true })) })
    await openAccion('ctrl-c', 'w1:p5')
    expect(act.error).toBe('Ese workspace está protegido')
  })

  it('un error del servidor se traduce y no se confirma dos veces', async () => {
    const f = api({ terminalCtrlC: vi.fn().mockRejectedValue(new ApiError(409, 'la terminal cambió, revisala de nuevo')) })
    await openAccion('ctrl-c', 'w1:p5')
    await confirmAccion()
    expect(act.phase).toBe('error')
    expect(act.error).toBe('La terminal cambió. Revisala de nuevo')
    await confirmAccion()
    expect(f.terminalCtrlC).toHaveBeenCalledTimes(1)
  })
})

describe('cerrar una terminal', () => {
  it('en el prompt se cierra sin preguntar', async () => {
    const f = api({})
    await openAccion('cerrar', 'w1:p5')
    expect(f.cerrarTerminal).toHaveBeenCalledWith({ id: expect.any(String), pane_id: 'w1:p5', huella: 'h1' })
    expect(act.listoTxt).toBe('Terminal cerrada')
  })

  it.each(['pestana', 'espacio'] as const)('en el prompt pero se lleva la %s: pide confirmar', async (cierra) => {
    const f = api({ previewTerminal: vi.fn().mockResolvedValue(preview({ cierra })) })
    await openAccion('cerrar', 'w1:p5')
    expect(act.phase).toBe('ready')
    expect(f.cerrarTerminal).not.toHaveBeenCalled()
    await confirmAccion()
    expect(f.cerrarTerminal).toHaveBeenCalledTimes(1)
  })

  it('la nota de la hoja dice qué se cierra', () => {
    expect(notaCierre(preview({ cierra: 'pestana', tab: 'Logs' }))).toBe('Es la única terminal de su pestaña: se cierra la pestaña «Logs» entera.')
    expect(notaCierre(preview({ cierra: 'espacio', workspace: 'Back' }))).toBe('Es la única terminal del workspace: se cierra el workspace «Back» entero.')
    expect(notaCierre(preview({ cierra: 'terminal' }))).toBe('')
  })

  it('con algo corriendo pide confirmar y recién ahí cierra', async () => {
    const f = api({ previewTerminal: vi.fn().mockResolvedValue(preview({ estado: 'corriendo', proceso: 'npm run dev' })) })
    await openAccion('cerrar', 'w1:p5')
    expect(act.phase).toBe('ready')
    expect(f.cerrarTerminal).not.toHaveBeenCalled()
    await confirmAccion()
    expect(f.cerrarTerminal).toHaveBeenCalledTimes(1)
  })

  it('una terminal protegida no se cierra', async () => {
    const f = api({ previewTerminal: vi.fn().mockResolvedValue(preview({ protegida: true })) })
    await openAccion('cerrar', 'w1:p5')
    expect(act.phase).toBe('error')
    expect(f.cerrarTerminal).not.toHaveBeenCalled()
  })

  it('si el visor mostraba esa terminal, se cierra también', async () => {
    api({})
    openTerminal('w1:p5')
    expect(openTerminalId.value).toBe('w1:p5')
    await openAccion('cerrar', 'w1:p5')
    // En el celu el visor se abrió con una entrada de historial: cerrarlo es volver atrás.
    expect(history.back).toHaveBeenCalled()
  })

  it('el servidor que se niega a cerrar una sesión de Claude da un mensaje claro', () => {
    expect(terminalError(new ApiError(403, 'es una sesión de agente'))).toBe('Es una sesión de Claude: no se cierra desde acá')
  })
})

describe('mensajes de error', () => {
  it('traduce los códigos y no muestra texto crudo del servidor', () => {
    expect(terminalError(new ApiError(429, 'x', 23))).toContain('23 s')
    expect(terminalError(new ApiError(502, 'Las terminales no respondieron: socket /run/x'))).toBe('Las terminales no respondieron')
    expect(terminalError(new ApiError(403, 'escritura apagada'))).toBe('La escritura de terminales está apagada')
    expect(terminalError(new ApiError(409, 'hay un programa corriendo (vim): frenalo primero'))).toContain('frenalo primero')
    expect(terminalError(new ApiError(400, '<img onerror=x>'))).toBe('No se pudo hacer')
    expect(terminalError(new Error('boom'))).toBe('No pude conectar con el servidor')
  })
})
