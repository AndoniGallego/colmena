import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'

const getCambios = vi.fn()
vi.mock('../api/cambiosApi', () => ({ getCambios: (...a: unknown[]) => getCambios(...a) }))

import { cambios, cargarCambios, limpiarCambios } from './cambios'

const dato = (rama: string) => ({ repo: true, rama, base: 'main', commits: [], commits_total: 0, sin_guardar: 0, archivos: [], truncado: false })

beforeEach(() => {
  getCambios.mockReset()
  limpiarCambios()
})

describe('cargarCambios', () => {
  it('guarda lo que llega y apaga loading', async () => {
    getCambios.mockResolvedValue(dato('f'))
    const p = cargarCambios('s1')
    expect(cambios.loading).toBe(true)
    await p
    expect(cambios.loading).toBe(false)
    expect(cambios.data?.rama).toBe('f')
    expect(cambios.sid).toBe('s1')
    expect(getCambios).toHaveBeenCalledWith('s1', false)
  })

  it('guarda el detalle del error y conserva lo anterior', async () => {
    getCambios.mockResolvedValueOnce(dato('f'))
    await cargarCambios('s1')
    getCambios.mockRejectedValueOnce(new ApiError(403, 'No permitida'))
    await cargarCambios('s1', true)
    expect(cambios.error).toBe('No permitida')
    expect(cambios.data?.rama).toBe('f')
  })

  it('ignora la respuesta de una sesión que ya no es la actual', async () => {
    let resolver: (v: unknown) => void = () => {}
    getCambios.mockReturnValueOnce(new Promise((r) => (resolver = r)))
    const vieja = cargarCambios('s1')
    getCambios.mockResolvedValueOnce(dato('nueva'))
    await cargarCambios('s2')
    resolver(dato('vieja'))
    await vieja
    expect(cambios.data?.rama).toBe('nueva')
    expect(cambios.sid).toBe('s2')
  })

  it('cambiar de sesión descarta los datos de la anterior', async () => {
    getCambios.mockResolvedValueOnce(dato('f'))
    await cargarCambios('s1')
    getCambios.mockReturnValueOnce(new Promise(() => {}))
    void cargarCambios('s2')
    expect(cambios.data).toBeNull()
  })
})
