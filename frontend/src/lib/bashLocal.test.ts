import { describe, expect, it } from 'vitest'
import { bashLocal } from './bashLocal'

describe('bashLocal', () => {
  it('reconoce el comando corrido con !', () => {
    expect(bashLocal('<bash-input>git status</bash-input>')).toEqual({ tipo: 'comando', texto: 'git status', error: '' })
  })
  it('reconoce la salida y el error', () => {
    expect(bashLocal('<bash-stdout>a\nb</bash-stdout><bash-stderr>uy</bash-stderr>')).toEqual({ tipo: 'salida', texto: 'a\nb', error: 'uy' })
  })
  it('salida vacía', () => {
    expect(bashLocal('<bash-stdout></bash-stdout><bash-stderr></bash-stderr>')).toEqual({ tipo: 'salida', texto: '', error: '' })
  })
  it('un mensaje normal no es bash', () => {
    expect(bashLocal('hola <bash-input>x</bash-input>')).toBeNull()
    expect(bashLocal('hola')).toBeNull()
  })
})
