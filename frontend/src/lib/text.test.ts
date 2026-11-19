import { describe, expect, it } from 'vitest'
import { capitalize } from './text'

describe('capitalize', () => {
  it('sube solo la primera letra', () => {
    expect(capitalize('en espera')).toBe('En espera')
    expect(capitalize('Ya está')).toBe('Ya está')
    expect(capitalize('')).toBe('')
    expect(capitalize('1 bloqueado')).toBe('1 bloqueado')
  })
})
