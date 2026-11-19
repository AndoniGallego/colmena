import { describe, expect, it } from 'vitest'
import { resizeAction } from './pegado'

const content = { id: 'thread' }
const scroller = { id: 'scroll' }

describe('resizeAction', () => {
  it('pegado al fondo: el composer que crece (visor más chico) vuelve al fondo', () => {
    expect(resizeAction(true, [scroller], content)).toBe('bottom')
  })
  it('pegado al fondo: contenido nuevo también', () => expect(resizeAction(true, [content], content)).toBe('bottom'))
  it('scrolleado arriba: el visor que cambia no mueve nada ni ofrece saltar', () => {
    expect(resizeAction(false, [scroller], content)).toBeNull()
  })
  it('scrolleado arriba: contenido nuevo ofrece "Ir al final"', () => {
    expect(resizeAction(false, [scroller, content], content)).toBe('jump')
  })
})
