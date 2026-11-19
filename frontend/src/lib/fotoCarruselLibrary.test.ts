import { describe, expect, it, vi } from 'vitest'
import { actVerEnBiblioteca } from './fotoCarruselLibrary'

describe('actVerEnBiblioteca', () => {
  it('con id válido llama openInLibrary y emitClose', () => {
    const openInLibrary = vi.fn()
    const emitClose = vi.fn()
    actVerEnBiblioteca('abc', openInLibrary, emitClose)
    expect(openInLibrary).toHaveBeenCalledTimes(1)
    expect(openInLibrary).toHaveBeenCalledWith('abc')
    expect(emitClose).toHaveBeenCalledTimes(1)
  })

  it('sin id no hace nada', () => {
    const openInLibrary = vi.fn()
    const emitClose = vi.fn()
    actVerEnBiblioteca(undefined, openInLibrary, emitClose)
    expect(openInLibrary).not.toHaveBeenCalled()
    expect(emitClose).not.toHaveBeenCalled()
  })

  it('con id vacío no hace nada', () => {
    const openInLibrary = vi.fn()
    const emitClose = vi.fn()
    actVerEnBiblioteca('', openInLibrary, emitClose)
    expect(openInLibrary).not.toHaveBeenCalled()
    expect(emitClose).not.toHaveBeenCalled()
  })
})
