import { describe, expect, it } from 'vitest'
import { ordenDeCierre } from './notificaciones'

describe('ordenDeCierre', () => {
  it('arma el mensaje por tags', () => {
    expect(ordenDeCierre({ tags: ['ses-abc', 'mr-1:2'] })).toEqual({
      type: 'orq-cerrar',
      tags: ['ses-abc', 'mr-1:2'],
    })
  })

  it('sigue armando por destino', () => {
    expect(ordenDeCierre({ session_id: 'abc' })).toEqual({ type: 'orq-cerrar', session_id: 'abc' })
  })
})
