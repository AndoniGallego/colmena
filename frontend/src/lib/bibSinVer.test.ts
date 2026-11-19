import { describe, expect, it } from 'vitest'
import { sumarSinVer, verItem, verSesion } from './bibSinVer'

const a = { id: 'a', session_id: 's1' }
const b = { id: 'b', session_id: 's2' }
const c = { id: 'c', session_id: null }

describe('bibSinVer', () => {
  it('suma lo que llega si no lo estás mirando en su sesión', () => {
    const m = sumarSinVer(new Map(), [a, b, c], null)
    expect([...m.keys()]).toEqual(['a', 'b', 'c'])
  })
  it('lo que llega de la sesión abierta ya cuenta como visto', () => {
    const m = sumarSinVer(new Map(), [a, b], 's1')
    expect([...m.keys()]).toEqual(['b'])
  })
  it('abrir el chat de una sesión saca sus ítems', () => {
    const m = verSesion(sumarSinVer(new Map(), [a, b, c], null), 's1')
    expect([...m.keys()]).toEqual(['b', 'c'])
  })
  it('abrir un ítem lo saca', () => {
    expect([...verItem(sumarSinVer(new Map(), [a, b], null), 'b').keys()]).toEqual(['a'])
  })
  it('no duplica ni muta el original', () => {
    const base = sumarSinVer(new Map(), [a], null)
    const m = sumarSinVer(base, [a, b], null)
    expect(base.size).toBe(1)
    expect(m.size).toBe(2)
  })
})
