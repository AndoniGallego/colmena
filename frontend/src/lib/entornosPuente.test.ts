import { describe, expect, it, vi } from 'vitest'
import { SOLO_APP, crearPuenteEntornos } from './entornosPuente'

describe('entornosPuente', () => {
  it('en el programa usa los cuatro comandos', async () => {
    const invoke = vi.fn().mockResolvedValue({ notebook: 'usuario@192.168.1.50', tuneles: {} })
    const p = crearPuenteEntornos({ __TAURI__: { core: { invoke } } } as unknown as Window)
    await p.estado()
    await p.abrir('tienda', [8080, 8092], 8080)
    await p.cerrar('tienda')
    await p.ajusteNotebook()
    expect(p.enPrograma).toBe(true)
    expect(invoke.mock.calls).toEqual([
      ['entornos_estado'],
      ['entorno_abrir', { nombre: 'tienda', puertos: [8080, 8092], principal: 8080 }],
      ['entorno_cerrar', { nombre: 'tienda' }],
      ['abrir_ajuste_notebook'],
    ])
  })

  it('no invoca con un nombre inválido y pasa los errores de Rust como Error', async () => {
    const invoke = vi.fn().mockRejectedValue('el puerto 8080 ya está en uso en esta PC')
    const p = crearPuenteEntornos({ __TAURI__: { core: { invoke } } } as unknown as Window)
    await expect(p.abrir('../x', [8080], 8080)).rejects.toThrow('nombre inválido')
    expect(invoke).not.toHaveBeenCalled()
    await expect(p.abrir('tienda', [8080], 8080)).rejects.toThrow('el puerto 8080 ya está en uso en esta PC')
  })

  it('cerrar y ajusteNotebook pasan el rechazo de invoke como Error con el mismo texto', async () => {
    const cerrarMsg = 'fallo al cerrar'
    const ajusteMsg = 'fallo ajuste'
    const invoke = vi.fn().mockImplementation((cmd: string) => {
      if (cmd === 'entorno_cerrar') return Promise.reject(cerrarMsg)
      if (cmd === 'abrir_ajuste_notebook') return Promise.reject(ajusteMsg)
      return Promise.resolve({ notebook: '', tuneles: {} })
    })
    const p = crearPuenteEntornos({ __TAURI__: { core: { invoke } } } as unknown as Window)
    let cerrarErr: unknown
    await p.cerrar('tienda').catch((e) => {
      cerrarErr = e
    })
    expect(cerrarErr).toBeInstanceOf(Error)
    expect((cerrarErr as Error).message).toBe(cerrarMsg)
    await expect(p.ajusteNotebook()).rejects.toThrow(ajusteMsg)
  })

  it('en el navegador queda en solo lectura', async () => {
    const p = crearPuenteEntornos({} as Window)
    expect(p.enPrograma).toBe(false)
    expect(await p.estado()).toEqual({ notebook: '', tuneles: {} })
    await expect(p.abrir('tienda', [8080], 8080)).rejects.toThrow(SOLO_APP)
  })
})
