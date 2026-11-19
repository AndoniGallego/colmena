import { describe, expect, it } from 'vitest'
import { esSesionTerminal, esTerminalPropia } from './terminalPropia'

describe('esTerminalPropia', () => {
  it('acepta espacios y líneas del guardián', () => {
    expect(esTerminalPropia('g1')).toBe(true)
    expect(esTerminalPropia('g12:p3')).toBe(true)
    expect(esTerminalPropia('g0:t99')).toBe(true)
  })

  it('rechaza ids de Herdr y basura', () => {
    for (const id of ['w1:p1', 'g', 'gabc', 'g1:x2', 'g1:p', null, undefined, '']) expect(esTerminalPropia(id)).toBe(false)
  })
})

describe('esSesionTerminal', () => {
  it('solo acepta g<N>:p<M>', () => {
    expect(esSesionTerminal('g1:p7')).toBe(true)
    for (const id of ['g1', 'g1:t3', 'w1:p1', 'g1:p', null, undefined, '']) expect(esSesionTerminal(id)).toBe(false)
  })
})
