import { describe, expect, it } from 'vitest'
import { composerKeys, enterSends, MAX_TEXTO, newId, textoProblem } from './reply'

const key = (over = {}) => ({ key: 'Enter', shiftKey: false, isComposing: false, ...over })

describe('textoProblem', () => {
  it('vacío o solo espacios', () => {
    expect(textoProblem('')).not.toBeNull()
    expect(textoProblem(' \n ')).not.toBeNull()
  })
  it('límite', () => {
    expect(textoProblem('x'.repeat(MAX_TEXTO))).toBeNull()
    expect(textoProblem('x'.repeat(MAX_TEXTO + 1))).toContain(String(MAX_TEXTO))
  })
})

describe('enterSends', () => {
  it('Enter envía en desktop', () => expect(enterSends(key(), true)).toBe(true))
  it('Shift+Enter es salto de línea', () => expect(enterSends(key({ shiftKey: true }), true)).toBe(false))
  it('no envía mientras compone (IME)', () => expect(enterSends(key({ isComposing: true }), true)).toBe(false))
  it('en táctil Enter no envía', () => expect(enterSends(key(), false)).toBe(false))
  it('otras teclas no envían', () => expect(enterSends(key({ key: 'a' }), true)).toBe(false))
  it('en táctil, trabajando, Enter encola', () => expect(enterSends(key(), false, true)).toBe(true))
  it('en táctil, trabajando, no encola mientras compone', () => expect(enterSends(key({ isComposing: true }), false, true)).toBe(false))
})

describe('composerKeys', () => {
  const base = { working: true, blocked: false, texto: '', files: 0 }
  it('trabajando y vacío: la tecla grande frena', () => {
    expect(composerKeys(base)).toEqual({ key: 'stop', queues: true })
  })
  it('trabajando con texto: la tecla vuelve a ser Enter y lo escrito se encola', () => {
    expect(composerKeys({ ...base, texto: 'hola' })).toEqual({ key: 'send', queues: true })
  })
  it('trabajando con solo espacios: sigue el freno', () => expect(composerKeys({ ...base, texto: '  ' })).toEqual({ key: 'stop', queues: true }))
  it('trabajando con solo adjuntos: Enter', () => expect(composerKeys({ ...base, files: 1 })).toEqual({ key: 'send', queues: true }))
  it('sin trabajar: enviar', () => {
    expect(composerKeys({ ...base, working: false, texto: 'x' })).toEqual({ key: 'send', queues: false })
    expect(composerKeys({ ...base, working: false })).toEqual({ key: 'send', queues: false })
  })
  it('bloqueada no ofrece frenar', () => {
    expect(composerKeys({ ...base, blocked: true })).toEqual({ key: 'send', queues: false })
    expect(composerKeys({ ...base, blocked: true, texto: 'x' })).toEqual({ key: 'send', queues: false })
  })
})

describe('newId', () => {
  const ID = /^[A-Za-z0-9_-]{8,64}$/
  it('cumple el formato del servidor y no se repite', () => {
    expect(newId()).toMatch(ID)
    expect(newId()).not.toBe(newId())
  })
  it('sin randomUUID cae a getRandomValues', () => {
    const real = crypto.randomUUID
    Object.defineProperty(crypto, 'randomUUID', { value: undefined, configurable: true })
    try {
      expect(newId()).toMatch(ID)
    } finally {
      Object.defineProperty(crypto, 'randomUUID', { value: real, configurable: true })
    }
  })
})
