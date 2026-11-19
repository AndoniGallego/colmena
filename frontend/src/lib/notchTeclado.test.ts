// @vitest-environment jsdom
import { describe, expect, it } from 'vitest'
import { esCampoTextoNotch } from './notchTeclado'

describe('notchTeclado', () => {
  it('detecta input, textarea y contenteditable', () => {
    const input = document.createElement('input')
    const area = document.createElement('textarea')
    const edit = document.createElement('div')
    edit.setAttribute('contenteditable', 'true')
    const div = document.createElement('div')
    expect(esCampoTextoNotch(input)).toBe(true)
    expect(esCampoTextoNotch(area)).toBe(true)
    expect(esCampoTextoNotch(edit)).toBe(true)
    expect(esCampoTextoNotch(div)).toBe(false)
  })

  it('detecta foco dentro de un input anidado', () => {
    const wrap = document.createElement('div')
    const input = document.createElement('input')
    wrap.appendChild(input)
    expect(esCampoTextoNotch(input)).toBe(true)
  })
})
