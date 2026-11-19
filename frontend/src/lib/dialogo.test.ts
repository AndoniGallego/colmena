import { describe, expect, it } from 'vitest'
import { ApiError, type DialogView } from '../api/types'
import { canApprove, dialogChanged, isModeChoice, needsPin, pinCopy, freezeSent, huellaOf, normalizeDialog, otroProblem, outcomeFor, permisoBody, preguntaBody, screenText, wantsComposer } from './dialogo'

const permisoRaw = (over: Record<string, unknown> = {}) => ({
  tipo: 'permiso',
  huella: 'h1',
  pane_id: 'w1:p1',
  permiso: { herramienta: 'Bash', detalle: 'ls', descripcion: 'Lista', completo: true, opciones: ['si', 'si_siempre', 'no'], regla: 'ls *', mas_en_terminal: true, ...over },
})
const preguntaRaw = (over: Record<string, unknown> = {}) => ({
  tipo: 'pregunta',
  huella: 'h2',
  pane_id: 'w1:p1',
  pregunta: { preguntas: [{ header: 'Color', texto: '¿Cuál?', multi: false, otro: true, opciones: [{ label: 'Rojo', descripcion: 'd' }, { label: 'Verde', descripcion: '' }], ...over }] },
})

const permiso = normalizeDialog(permisoRaw())
const pregunta = normalizeDialog(preguntaRaw())

describe('normalizeDialog', () => {
  it('reads permission and question', () => {
    expect(permiso.tipo).toBe('permiso')
    expect(pregunta.tipo).toBe('pregunta')
    expect(normalizeDialog({ tipo: 'ninguno' })).toEqual({ tipo: 'ninguno' })
  })
  it('fails closed to the read-only view', () => {
    expect(normalizeDialog(null).tipo).toBe('desconocido')
    expect(normalizeDialog(permisoRaw({ herramienta: 'Read' })).tipo).toBe('desconocido')
    expect(normalizeDialog(permisoRaw({ opciones: ['si'] })).tipo).toBe('desconocido')
    expect(normalizeDialog({ ...permisoRaw(), huella: '' }).tipo).toBe('desconocido')
    expect(normalizeDialog(preguntaRaw({ multi: 'si' })).tipo).toBe('desconocido')
    expect(normalizeDialog({ tipo: 'permiso_nuevo', huella: 'x', pane_id: 'p' }).tipo).toBe('desconocido')
  })
  it('drops unknown choices instead of offering them', () => {
    const v = normalizeDialog(permisoRaw({ opciones: ['si', 'modo_auto', 'no'] }))
    expect(v.tipo === 'permiso' && v.permiso.opciones).toEqual(['si', 'no'])
  })
  it('keeps the terminal screen of an unknown dialog', () => {
    expect(normalizeDialog({ tipo: 'desconocido', pane_id: 'p', pantalla: 'raro' })).toEqual({ tipo: 'desconocido', paneId: 'p', pantalla: 'raro' })
  })
  it('normaliza pedido y descarta uno sin id', () => {
    expect(normalizeDialog({ tipo: 'pedido', pedido: { id: 'p1', estado: 'abierto', regla: null } }).tipo).toBe('pedido')
    expect(normalizeDialog({ tipo: 'pedido', pedido: {} }).tipo).toBe('desconocido')
  })
})

describe('permisoBody', () => {
  it('builds the plain approval', () => {
    expect(permisoBody(permiso, 's1', 'id-12345678', 'si')).toEqual({ id: 'id-12345678', session_id: 's1', pane_id: 'w1:p1', huella: 'h1', tipo: 'permiso', permiso: 'si' })
  })
  it('builds no body for si_siempre without a PIN', () => {
    expect(permisoBody(permiso, 's1', 'id-12345678', 'si_siempre')).toBeNull()
    expect(permisoBody(permiso, 's1', 'id-12345678', 'si_siempre', '')).toBeNull()
    expect(permisoBody(permiso, 's1', 'id-12345678', 'si_siempre', '4321')?.pin).toBe('4321')
  })
  it('never puts a PIN on the other choices', () => {
    expect(permisoBody(permiso, 's1', 'id-12345678', 'no', '4321')).not.toHaveProperty('pin')
  })
  it('refuses a choice the server did not offer or an incomplete command', () => {
    const only = normalizeDialog(permisoRaw({ opciones: ['si', 'no'] }))
    expect(permisoBody(only, 's1', 'id-12345678', 'si_siempre', '4321')).toBeNull()
    const cut = normalizeDialog(permisoRaw({ completo: false }))
    expect(canApprove((cut as Extract<DialogView, { tipo: 'permiso' }>).permiso, 'si')).toBe(false)
    expect(canApprove((cut as Extract<DialogView, { tipo: 'permiso' }>).permiso, 'no')).toBe(true)
    expect(permisoBody(pregunta, 's1', 'id-12345678', 'si')).toBeNull()
  })
})

describe('mode choices', () => {
  const modos = normalizeDialog(permisoRaw({ opciones: ['si', 'si_siempre', 'si_auto', 'no'] }))
  const edits = normalizeDialog(permisoRaw({ herramienta: 'Edit', archivo: '/a/b.txt', opciones: ['si', 'si_ediciones', 'no'], regla: null }))
  it('reads them as offered choices', () => {
    expect(modos.tipo === 'permiso' && modos.permiso.opciones).toEqual(['si', 'si_siempre', 'si_auto', 'no'])
    expect(edits.tipo === 'permiso' && edits.permiso.opciones).toEqual(['si', 'si_ediciones', 'no'])
  })
  it('never builds a body without the PIN', () => {
    for (const c of ['si_auto', 'si_ediciones'] as const) {
      expect(needsPin(c)).toBe(true)
      expect(isModeChoice(c)).toBe(true)
    }
    expect(permisoBody(modos, 's1', 'id-12345678', 'si_auto')).toBeNull()
    expect(permisoBody(modos, 's1', 'id-12345678', 'si_auto', '')).toBeNull()
    expect(permisoBody(modos, 's1', 'id-12345678', 'si_auto', '4321')).toMatchObject({ permiso: 'si_auto', pin: '4321' })
    expect(permisoBody(edits, 's1', 'id-12345678', 'si_ediciones', '4321')).toMatchObject({ permiso: 'si_ediciones', pin: '4321' })
  })
  it('refuses a mode the server did not offer for that tool', () => {
    expect(permisoBody(edits, 's1', 'id-12345678', 'si_auto', '4321')).toBeNull()
    expect(permisoBody(modos, 's1', 'id-12345678', 'si_ediciones', '4321')).toBeNull()
  })
  it('refuses a mode on an incomplete command', () => {
    const cut = normalizeDialog(permisoRaw({ opciones: ['si', 'si_auto', 'no'], completo: false }))
    expect(permisoBody(cut, 's1', 'id-12345678', 'si_auto', '4321')).toBeNull()
  })
  it('explains the consequence in the sheet', () => {
    expect(pinCopy('si_auto', null).note).toContain('deja de pedirte permiso para comandos')
    expect(pinCopy('si_ediciones', null).note).toContain('deja de pedirte permiso para ediciones')
    expect(pinCopy('si_siempre', 'ls *')).toMatchObject({ code: 'ls *', confirm: 'Confirmar y permitir siempre' })
  })
})

describe('preguntaBody', () => {
  it('maps the radio to an index', () => {
    expect(preguntaBody(pregunta, 's1', 'id-12345678', { opciones: [[1]] })?.respuestas).toEqual([{ opciones: [1] }])
  })
  it('sends the typed answer trimmed', () => {
    expect(preguntaBody(pregunta, 's1', 'id-12345678', { otro: '  Frutilla ' })?.respuestas).toEqual([{ otro: 'Frutilla' }])
  })
  it('rejects out of range, empty, and no selection', () => {
    expect(preguntaBody(pregunta, 's1', 'id-12345678', { opciones: [[2]] })).toBeNull()
    expect(preguntaBody(pregunta, 's1', 'id-12345678', { opciones: [[-1]] })).toBeNull()
    expect(preguntaBody(pregunta, 's1', 'id-12345678', { otro: '   ' })).toBeNull()
    expect(preguntaBody(pregunta, 's1', 'id-12345678', null)).toBeNull()
    expect(preguntaBody(permiso, 's1', 'id-12345678', { opciones: [[0]] })).toBeNull()
  })
})

const q = (multi: boolean, n = 3) => ({ header: 'H', texto: '¿Q?', multi, otro: false, opciones: Array.from({ length: n }, (_, i) => ({ label: `o${i}`, descripcion: '' })) })
const several = (...qs: unknown[]) => normalizeDialog({ tipo: 'pregunta', huella: 'h', pane_id: 'w:p', pregunta: { preguntas: qs } })
const body = (v: ReturnType<typeof several>, opciones: number[][]) => preguntaBody(v, 's1', 'id-12345678', { opciones })?.respuestas ?? null

describe('multi and several questions', () => {
  it('accepts multi and up to four questions, never more', () => {
    expect(several(q(true)).tipo).toBe('pregunta')
    expect(several(q(false), q(true), q(false), q(true)).tipo).toBe('pregunta')
    expect(several(q(false), q(false), q(false), q(false), q(false)).tipo).toBe('desconocido')
    expect(several().tipo).toBe('desconocido')
    expect(several(q(false), { ...q(true), opciones: [] }).tipo).toBe('desconocido')
  })
  it('offers the typed answer only for a single simple question', () => {
    const one = several({ ...q(false), otro: true })
    const two = several({ ...q(false), otro: true }, q(false))
    const multi = several({ ...q(true), otro: true })
    expect(one.tipo === 'pregunta' && one.pregunta.preguntas[0].otro).toBe(true)
    expect(two.tipo === 'pregunta' && two.pregunta.preguntas[0].otro).toBe(false)
    expect(multi.tipo === 'pregunta' && multi.pregunta.preguntas[0].otro).toBe(false)
    expect(preguntaBody(two, 's1', 'id-12345678', { otro: 'x' })).toBeNull()
    expect(preguntaBody(multi, 's1', 'id-12345678', { otro: 'x' })).toBeNull()
  })
  it('sends one entry per question with the picks sorted', () => {
    expect(body(several(q(false), q(true)), [[1], [2, 0]])).toEqual([{ opciones: [1] }, { opciones: [0, 2] }])
  })
  it('rejects empty, repeated, extra, missing and out of range picks', () => {
    const v = several(q(false), q(true))
    for (const bad of [[[1], []], [[1], [0, 0]], [[0, 1], [0]], [[1]], [[1], [3]], [[1], [0], [0]], [[], [0]]]) expect(body(v, bad)).toBeNull()
  })
  it('allows a multi selection of up to six picks', () => {
    expect(body(several(q(true, 6)), [[0, 1, 2, 3, 4, 5]])).toEqual([{ opciones: [0, 1, 2, 3, 4, 5] }])
    expect(body(several(q(true, 6)), [[0, 1, 2, 3, 4, 5, 6]])).toBeNull()
  })
})

describe('otroProblem', () => {
  it('validates length and characters', () => {
    expect(otroProblem('ok')).toBeNull()
    expect(otroProblem('')).not.toBeNull()
    expect(otroProblem('a\nb')).not.toBeNull()
    expect(otroProblem('a\u001bb')).not.toBeNull()
    expect(otroProblem('x'.repeat(500))).toBeNull()
    expect(otroProblem('x'.repeat(501))).not.toBeNull()
  })
})

describe('outcomeFor', () => {
  it('maps each status', () => {
    expect(outcomeFor(new ApiError(409, 'Ya se respondió')).kind).toBe('done')
    expect(outcomeFor(new ApiError(409, 'El diálogo cambió')).kind).toBe('stale')
    expect(outcomeFor(new ApiError(502, 'Quedó a medio responder: terminá en la terminal')).kind).toBe('half')
    expect(outcomeFor(new ApiError(401, 'PIN incorrecto')).kind).toBe('pin')
    expect(outcomeFor(new ApiError(429, 'Demasiados intentos', 30))).toMatchObject({ kind: 'limit', retryAfter: 30 })
    expect(outcomeFor(new ApiError(400, 'cuerpo inválido')).kind).toBe('error')
    expect(outcomeFor(new Error('x')).kind).toBe('error')
  })
})

describe('misc', () => {
  it('asks for the composer after a refusal or an interruption', () => {
    expect(wantsComposer('no', false)).toBe(true)
    expect(wantsComposer('si', true)).toBe(true)
    expect(wantsComposer('si', false)).toBe(false)
  })
  it('trims blank edges of the screen', () => {
    expect(screenText('\n\n a\nb \n\n')).toBe(' a\nb ')
    expect(screenText('1\n2\n3', 2)).toBe('2\n3')
  })
})

describe('huella guards', () => {
  it('detects a swap only between two non-empty fingerprints', () => {
    expect(dialogChanged('a', 'b')).toBe(true)
    expect(dialogChanged('a', 'a')).toBe(false)
    expect(dialogChanged('', 'b')).toBe(false)
    expect(dialogChanged('a', '')).toBe(false)
  })
  it('reads the fingerprint of any view', () => {
    expect(huellaOf(permiso)).toBe('h1')
    expect(huellaOf(null)).toBe('')
    expect(huellaOf({ tipo: 'ninguno' })).toBe('')
  })
  it('freezes a prompt that already received keys into the read-only view', () => {
    expect(freezeSent(permiso, ['h1']).tipo).toBe('desconocido')
    expect(freezeSent(permiso, ['otra']).tipo).toBe('permiso')
  })
  it('maps "ya se mandó" to a half-done outcome, not a reloadable stale one', () => {
    expect(outcomeFor(new ApiError(409, 'Ya se mandó una respuesta: mirá la terminal')).kind).toBe('half')
  })
})
