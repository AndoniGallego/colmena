import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'

const getAtajos = vi.fn()
const putAtajos = vi.fn()

vi.mock('./app', () => ({
  auth: { value: 'ready' },
  getAtajos: (...a: unknown[]) => getAtajos(...a),
  setAtajos: (...a: unknown[]) => putAtajos(...a),
}))

const { atajosGuardados, atajosError, comboDe, etiquetaDe, cargarAtajos, cambiarAtajo, restaurarAtajo, capturandoAtajo } = await import('./atajos')

describe('atajos', () => {
  beforeEach(() => {
    getAtajos.mockReset()
    putAtajos.mockReset()
    atajosGuardados.value = {}
    atajosError.value = ''
    capturandoAtajo.value = false
  })

  it('sin nada guardado usa los originales', () => {
    expect(comboDe('buscador')).toBe('mod+k')
    expect(comboDe('minimizar-preguntas')).toBe('m')
  })

  it('carga lo guardado en el servidor', async () => {
    getAtajos.mockResolvedValueOnce({ buscador: 'mod+j' })
    await cargarAtajos()
    expect(comboDe('buscador')).toBe('mod+j')
    expect(comboDe('dictar')).toBe('mod+shift+space')
  })

  it('si el servidor falla quedan los originales', async () => {
    getAtajos.mockRejectedValueOnce(new Error('x'))
    await cargarAtajos()
    expect(comboDe('buscador')).toBe('mod+k')
  })

  it('ignora ids o combinaciones raras que vengan del servidor', async () => {
    getAtajos.mockResolvedValueOnce({ otro: 'mod+j', buscador: 5, dictar: 'mod+alt+d' })
    await cargarAtajos()
    expect(atajosGuardados.value).toEqual({ dictar: 'mod+alt+d' })
  })

  it('cambiar guarda solo lo distinto del original, con PUT del mapa completo', async () => {
    putAtajos.mockResolvedValue(undefined)
    expect(await cambiarAtajo('buscador', 'mod+j')).toBe(true)
    expect(putAtajos).toHaveBeenLastCalledWith({ buscador: 'mod+j' })
    expect(etiquetaDe('buscador', false)).toBe('Ctrl J')
    expect(await cambiarAtajo('buscador', 'mod+k')).toBe(true)
    expect(putAtajos).toHaveBeenLastCalledWith({})
    expect(atajosGuardados.value).toEqual({})
  })

  it('volver al original borra la entrada', async () => {
    putAtajos.mockResolvedValue(undefined)
    atajosGuardados.value = { buscador: 'mod+j', dictar: 'mod+alt+d' }
    await restaurarAtajo('buscador')
    expect(putAtajos).toHaveBeenLastCalledWith({ dictar: 'mod+alt+d' })
    expect(comboDe('buscador')).toBe('mod+k')
  })

  it('si el PUT falla vuelve atrás y avisa', async () => {
    putAtajos.mockRejectedValueOnce(new ApiError(422, 'no'))
    expect(await cambiarAtajo('buscador', 'mod+j')).toBe(false)
    expect(comboDe('buscador')).toBe('mod+k')
    expect(atajosError.value).toBe('No pude guardar el atajo')
  })
})
