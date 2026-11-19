import { describe, expect, it } from 'vitest'
import { avisoStatus, toAvisoRef } from './avisoCard'

describe('toAvisoRef', () => {
  it('acepta pane o session', () => {
    expect(toAvisoRef({ pane_id: 'w1:p1', tipo: 'fin', titulo: 'Login', texto: 'Listo' })).toMatchObject({
      pane_id: 'w1:p1',
      tipo: 'fin',
    })
    expect(toAvisoRef({ session_id: 'sid', tipo: 'info', titulo: 'X', texto: 'Y' })?.session_id).toBe('sid')
  })

  it('rechaza sin identificador o tipo inválido', () => {
    expect(toAvisoRef({ tipo: 'fin', titulo: 'a', texto: 'b' })).toBeNull()
    expect(toAvisoRef({ pane_id: 'w1:p1', tipo: 'otro', titulo: 'a', texto: 'b' })).toBeNull()
  })

  it('mapea tipo a status visual', () => {
    expect(avisoStatus('pregunta')).toBe('blocked')
    expect(avisoStatus('fin')).toBe('done')
  })
})
