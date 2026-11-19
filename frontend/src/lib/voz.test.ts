import { describe, expect, it } from 'vitest'
import { extFor, formatClock, insertAtCursor, isIOS, isVozShortcut, kindFromMediaError, kindFromStatus, pickMimeType, vozError } from './voz'

describe('pickMimeType', () => {
  it('Chrome: webm con opus', () => {
    expect(pickMimeType((t) => t.startsWith('audio/webm') || t === 'audio/ogg;codecs=opus')).toBe('audio/webm;codecs=opus')
  })
  it('iOS: solo mp4', () => {
    expect(pickMimeType((t) => t === 'audio/mp4')).toBe('audio/mp4')
  })
  it('si nada coincide deja elegir al navegador', () => {
    expect(pickMimeType(() => false)).toBe('')
  })
  it('un isTypeSupported que tira no rompe', () => {
    let n = 0
    expect(
      pickMimeType((t) => {
        if (n++ === 0) throw new Error('raro')
        return t === 'audio/mp4'
      }),
    ).toBe('audio/mp4')
  })
})

describe('extFor', () => {
  it('mapea el tipo a la extensión que el server espera', () => {
    expect(extFor('audio/webm;codecs=opus')).toBe('webm')
    expect(extFor('audio/mp4;codecs=mp4a.40.2')).toBe('m4a')
    expect(extFor('audio/ogg')).toBe('ogg')
    expect(extFor('')).toBe('webm')
  })
})

describe('insertAtCursor', () => {
  it('en el medio, con espacios de cortesía', () => {
    expect(insertAtCursor('hola mundo', 4, 4, 'qué lindo')).toEqual({ text: 'hola qué lindo mundo', cursor: 14 })
  })
  it('al final si no hay selección', () => {
    expect(insertAtCursor('hola', undefined, undefined, 'mundo')).toEqual({ text: 'hola mundo', cursor: 10 })
    expect(insertAtCursor('hola', null, null, 'mundo').text).toBe('hola mundo')
  })
  it('reemplaza la selección', () => {
    expect(insertAtCursor('uno XXX tres', 4, 7, 'dos')).toEqual({ text: 'uno dos tres', cursor: 7 })
  })
  it('sin espacio doble si ya hay espacio o salto de línea', () => {
    expect(insertAtCursor('hola ', 5, 5, 'mundo').text).toBe('hola mundo')
    expect(insertAtCursor('a\n', 2, 2, 'b').text).toBe('a\nb')
    expect(insertAtCursor('x', 0, 0, 'y').text).toBe('y x')
  })
  it('composer vacío y texto vacío', () => {
    expect(insertAtCursor('', 0, 0, ' hola ')).toEqual({ text: 'hola', cursor: 4 })
    expect(insertAtCursor('abc', 1, 1, '   ')).toEqual({ text: 'abc', cursor: 1 })
  })
  it('acota posiciones fuera de rango', () => {
    expect(insertAtCursor('ab', 99, 120, 'c').text).toBe('ab c')
    expect(insertAtCursor('ab', -5, 1, 'c').text).toBe('c b')
  })
})

describe('formatClock', () => {
  it('minutos y segundos', () => {
    expect(formatClock(0)).toBe('0:00')
    expect(formatClock(9.9)).toBe('0:09')
    expect(formatClock(75)).toBe('1:15')
    expect(formatClock(120)).toBe('2:00')
    expect(formatClock(-3)).toBe('0:00')
  })
})

describe('errores', () => {
  it('mapea nombres de error de getUserMedia', () => {
    expect(kindFromMediaError('NotAllowedError')).toBe('permiso')
    expect(kindFromMediaError('NotFoundError')).toBe('sin-microfono')
    expect(kindFromMediaError('NotReadableError')).toBe('mic-ocupado')
    expect(kindFromMediaError('Otra')).toBe('server')
  })
  it('mapea el status del server', () => {
    expect(kindFromStatus(409)).toBe('ocupada')
    expect(kindFromStatus(404)).toBe('deshabilitada')
    expect(kindFromStatus(413)).toBe('larga')
    expect(kindFromStatus(503)).toBe('modelo')
    expect(kindFromStatus(504)).toBe('tiempo')
    expect(kindFromStatus(0)).toBe('red')
    expect(kindFromStatus(500)).toBe('server')
  })
  it('el permiso explica cómo habilitarlo según la plataforma', () => {
    expect(vozError('permiso', { ios: true }).hint).toContain('Ajustes')
    expect(vozError('permiso', { ios: false }).hint).toContain('candado')
    expect(vozError('silencio').title).toBe('No se escuchó nada.')
  })
  it('detecta iOS, incluido el iPad que se hace pasar por Mac', () => {
    expect(isIOS('Mozilla/5.0 (iPhone; CPU iPhone OS 18_0)', '', 5)).toBe(true)
    expect(isIOS('Mozilla/5.0 (Macintosh)', 'MacIntel', 5)).toBe(true)
    expect(isIOS('Mozilla/5.0 (Windows NT 10.0)', 'Win32', 0)).toBe(false)
  })
})

describe('isVozShortcut', () => {
  const e = (o: Partial<KeyboardEvent>) => ({ code: 'Space', ctrlKey: true, shiftKey: true, altKey: false, metaKey: false, ...o })
  it('Ctrl+Shift+Espacio', () => {
    expect(isVozShortcut(e({}))).toBe(true)
  })
  it('no choca con otros atajos', () => {
    expect(isVozShortcut(e({ code: 'KeyM' }))).toBe(false)
    expect(isVozShortcut(e({ shiftKey: false }))).toBe(false)
    expect(isVozShortcut(e({ ctrlKey: false }))).toBe(false)
    expect(isVozShortcut(e({ altKey: true }))).toBe(false)
  })
})
