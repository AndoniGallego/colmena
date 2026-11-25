import { describe, expect, it } from 'vitest'
import { armarCombo, coincide, EDITABLES, etiquetaCombo, partesCombo, validarCombo } from './teclas'

const ev = (o: Partial<{ key: string; code: string; ctrlKey: boolean; metaKey: boolean; altKey: boolean; shiftKey: boolean }>) => ({
  key: '',
  code: '',
  ctrlKey: false,
  metaKey: false,
  altKey: false,
  shiftKey: false,
  ...o,
})
const originales = () => Object.fromEntries(EDITABLES.map((a) => [a.id, a.original]))

describe('armarCombo', () => {
  it('arma mod+tecla con Ctrl en Windows/Linux y ⌘ en Mac', () => {
    expect(armarCombo(ev({ key: 'k', ctrlKey: true }), false)).toBe('mod+k')
    expect(armarCombo(ev({ key: 'K', metaKey: true }), true)).toBe('mod+k')
  })
  it('ordena modificadores y nombra Espacio y Enter', () => {
    expect(armarCombo(ev({ key: ' ', code: 'Space', ctrlKey: true, shiftKey: true }), false)).toBe('mod+shift+space')
    expect(armarCombo(ev({ key: 'Enter', ctrlKey: true, altKey: true }), false)).toBe('mod+alt+enter')
  })
  it('con Shift o Alt usa la tecla física para letras y números', () => {
    expect(armarCombo(ev({ key: '!', code: 'Digit1', ctrlKey: true, shiftKey: true }), false)).toBe('mod+shift+1')
    expect(armarCombo(ev({ key: 'å', code: 'KeyA', altKey: true }), false)).toBe('alt+a')
  })
  it('devuelve null si solo se apretó un modificador o el modificador ajeno a la plataforma', () => {
    expect(armarCombo(ev({ key: 'Control', ctrlKey: true }), false)).toBeNull()
    expect(armarCombo(ev({ key: 'Shift', shiftKey: true }), false)).toBeNull()
    expect(armarCombo(ev({ key: 'k', metaKey: true }), false)).toBeNull()
    expect(armarCombo(ev({ key: 'k', ctrlKey: true }), true)).toBeNull()
  })
})

describe('coincide', () => {
  it('reconoce la combinación', () => {
    expect(coincide(ev({ key: 'k', ctrlKey: true }), 'mod+k', false)).toBe(true)
    expect(coincide(ev({ key: 'k', ctrlKey: true, shiftKey: true }), 'mod+k', false)).toBe(false)
    expect(coincide(ev({ key: 'j', ctrlKey: true }), 'mod+k', false)).toBe(false)
  })
  it('una letra sola no se dispara con Ctrl, Alt ni ⌘ pero tolera Shift', () => {
    expect(coincide(ev({ key: 'm' }), 'm', false)).toBe(true)
    expect(coincide(ev({ key: 'M', shiftKey: true }), 'm', false)).toBe(true)
    expect(coincide(ev({ key: 'm', ctrlKey: true }), 'm', false)).toBe(false)
  })
})

describe('mostrar', () => {
  it('parte la combinación para los <kbd>', () => {
    expect(partesCombo('mod+shift+space', false)).toEqual(['Ctrl', 'Shift', 'Espacio'])
    expect(partesCombo('mod+k', true)).toEqual(['⌘', 'K'])
    expect(partesCombo('alt+enter', false)).toEqual(['Alt', 'Enter'])
  })
  it('etiqueta corta de una línea', () => {
    expect(etiquetaCombo('mod+k', false)).toBe('Ctrl K')
    expect(etiquetaCombo('mod+k', true)).toBe('⌘K')
  })
})

describe('validarCombo', () => {
  it('acepta una combinación libre', () => {
    expect(validarCombo('buscador', 'mod+j', originales(), false)).toBeNull()
  })
  it('pide modificador salvo en minimizar-preguntas', () => {
    expect(validarCombo('buscador', 'j', originales(), false)).toBe('Necesita Ctrl, Alt o Shift')
    expect(validarCombo('minimizar-preguntas', 'n', originales(), false)).toBeNull()
  })
  it('minimizar-preguntas no puede usar teclas que ya tienen otro uso en Te pregunta', () => {
    for (const k of ['1', '6', 'enter', 'tab', 'space'])
      expect(validarCombo('minimizar-preguntas', k, originales(), false)).toBe('Esa tecla ya tiene otro uso en Te pregunta')
    expect(validarCombo('minimizar-preguntas', '7', originales(), false)).toBeNull()
  })
  it('Shift solo con una letra no alcanza', () => {
    expect(validarCombo('buscador', 'shift+j', originales(), false)).toBe('Con Shift solo no alcanza: sumale Ctrl o Alt')
  })
  it('avisa si la usa otro atajo editable', () => {
    expect(validarCombo('buscador', 'mod+shift+space', originales(), false)).toBe('Ya la usa «Dictar por voz»')
  })
  it('Nueva terminal y comentar pueden compartir Ctrl+Enter (otro contexto), pero no con uno global', () => {
    expect(validarCombo('comentar', 'mod+enter', originales(), false)).toBeNull()
    expect(validarCombo('crear-terminal', 'mod+k', originales(), false)).toBe('Ya la usa «Abrir el buscador»')
  })
  it('rechaza los atajos reservados del navegador', () => {
    expect(validarCombo('buscador', 'mod+t', originales(), false)).toBe('El navegador usa Ctrl+T para abrir una pestaña')
    expect(validarCombo('buscador', 'mod+tab', originales(), false)).toContain('El navegador usa Ctrl+Tab')
    expect(validarCombo('buscador', 'alt+f4', originales(), false)).toContain('El navegador usa Alt+F4')
    expect(validarCombo('buscador', 'f5', originales(), false)).toContain('El navegador usa F5')
  })
})
