import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { PuenteEntornos } from '../lib/entornosPuente'
import { ErrorUsuario } from '../lib/errores'
import {
  abrirEntorno,
  abrirPuerto,
  cargarEntornos,
  cambiarNotebook,
  cerrarEntorno,
  entornos,
  esRutaEntornos,
  setDepsEntornos,
} from './entornos'

const tienda = {
  nombre: 'tienda',
  carpeta: '',
  principal: 8080,
  salud: null,
  apagado: false,
  servicios: [],
  puertos: [8080, 8092, 8093].map((puerto) => ({ puerto, servicio: 's', puerto_contenedor: null, abrible: true })),
}

function fake(over: Partial<PuenteEntornos> = {}) {
  const puente: PuenteEntornos = {
    enPrograma: true,
    estado: vi.fn().mockResolvedValue({ notebook: 'usuario@192.168.1.50', tuneles: {} }),
    abrir: vi.fn().mockResolvedValue({ estado: 'abierto', puertos: [8080], error: null }),
    cerrar: vi.fn().mockResolvedValue(undefined),
    ajusteNotebook: vi.fn().mockResolvedValue(undefined),
    ...over,
  }
  setDepsEntornos({ listar: vi.fn().mockResolvedValue({ entornos: [tienda], error: null }), puente })
  return puente
}

beforeEach(() => {
  Object.assign(entornos, {
    lista: [],
    error: '',
    abriendo: [],
    cerrando: [],
    errores: {},
    tuneles: {},
    notebook: '',
    cargando: false,
    enPrograma: false,
  })
})

describe('entornos state', () => {
  it('carga la lista y el estado de los túneles', async () => {
    fake()
    await cargarEntornos()
    expect(entornos).toMatchObject({ enPrograma: true, notebook: 'usuario@192.168.1.50', lista: [tienda], error: '', cargando: false })
  })

  it('en el navegador no pide estado', async () => {
    const p = fake({ enPrograma: false })
    await cargarEntornos()
    expect(p.estado).not.toHaveBeenCalled()
    expect(entornos.enPrograma).toBe(false)
  })

  it('abrir manda los puertos del túnel y el principal', async () => {
    const p = fake()
    await abrirEntorno(tienda)
    expect(p.abrir).toHaveBeenCalledWith('tienda', [8080, 8092, 8093], 8080)
    expect(p.estado).toHaveBeenCalled()
    expect(entornos.abriendo).toEqual([])
  })

  it('un puerto abre el navegador en ese puerto', async () => {
    const p = fake()
    await abrirPuerto(tienda, 8092)
    expect(p.abrir).toHaveBeenCalledWith('tienda', [8080, 8092, 8093], 8092)
  })

  it('dos clics abren un solo túnel', async () => {
    const p = fake()
    await Promise.all([abrirEntorno(tienda), abrirEntorno(tienda)])
    expect(p.abrir).toHaveBeenCalledTimes(1)
  })

  it('el error de puerto ocupado queda en la tarjeta y cerrar lo limpia', async () => {
    fake({
      abrir: vi.fn().mockRejectedValue(new ErrorUsuario('el puerto 8080 ya está en uso en esta PC')),
    })
    await abrirEntorno(tienda)
    expect(entornos.errores.tienda).toBe('el puerto 8080 ya está en uso en esta PC')
    await cerrarEntorno('tienda')
    expect(entornos.errores.tienda).toBeUndefined()
  })

  it('si cerrar falla guarda el error y refresca túneles', async () => {
    const cerrar = vi.fn().mockRejectedValue(new ErrorUsuario('no se pudo cerrar'))
    const estado = vi.fn().mockResolvedValue({ notebook: 'u@h', tuneles: { tienda: { estado: 'abierto', puertos: [8080], error: null } } })
    fake({ cerrar, estado })
    await cerrarEntorno('tienda')
    expect(cerrar).toHaveBeenCalledWith('tienda')
    expect(estado).toHaveBeenCalled()
    expect(entornos.errores.tienda).toBe('no se pudo cerrar')
  })

  it('reconoce la ruta /entornos', () => {
    expect(['/entornos', '/entornos/', '/', '/entornosx'].map(esRutaEntornos)).toEqual([true, true, false, false])
  })

  it('cargarEntornos con red caída muestra mensaje en castellano', async () => {
    const puente = fake({ enPrograma: false })
    setDepsEntornos({ listar: vi.fn().mockRejectedValue(new TypeError('Failed to fetch')), puente })
    await cargarEntornos()
    expect(entornos.error).toBe('No llego a Colmena. Revisá la conexión y probá de nuevo.')
  })

  it('cerrar marca cerrando hasta terminar', async () => {
    let resolveCerrar!: () => void
    const cerrar = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          resolveCerrar = resolve
        }),
    )
    fake({ cerrar })
    const pending = cerrarEntorno('tienda')
    expect(entornos.cerrando).toEqual(['tienda'])
    resolveCerrar()
    await pending
    expect(entornos.cerrando).toEqual([])
  })

  it('cambiarNotebook guarda el error en entornos.error', async () => {
    const p = fake({
      ajusteNotebook: vi.fn().mockRejectedValue(new ErrorUsuario('no se pudo guardar')),
    })
    cambiarNotebook()
    await new Promise((r) => setTimeout(r, 0))
    expect(p.ajusteNotebook).toHaveBeenCalled()
    expect(entornos.error).toBe('no se pudo guardar')
  })
})
