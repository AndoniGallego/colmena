// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'
import type { Kit } from '../api/kitApi'
import { abrirRegla, arreglar, cargarKit, cerrarRegla, closeKit, kit, kitOpen, openKit, resetKit, setKitApi } from './kit'

const kitRoto: Kit = { estado: { al_dia: false, problemas: ['Falta algo.'] }, reglas: [], skills: [], hooks: [] }
const kitOk: Kit = { ...kitRoto, estado: { al_dia: true, problemas: [] } }

const api = { getKit: vi.fn(), getRegla: vi.fn(), arreglarKit: vi.fn() }

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset())
  setKitApi(api)
  kit.data = null
  kit.error = ''
  kit.arreglando = false
  kit.errorArreglo = ''
  kit.regla = null
  kitOpen.value = false
})

describe('state/kit', () => {
  it('abre y cierra con historial', () => {
    openKit()
    expect(kitOpen.value).toBe(true)
    expect(history.state.orqKit).toBe(true)
    closeKit()
  })

  it('resetKit cierra y borra lo cargado (se perdió la sesión)', () => {
    openKit()
    kit.data = structuredClone(kitRoto)
    resetKit()
    expect(kitOpen.value).toBe(false)
    expect(kit.data).toBeNull()
  })

  it('cargarKit guarda los datos', async () => {
    api.getKit.mockResolvedValue(kitRoto)
    await cargarKit()
    expect(kit.data).toEqual(kitRoto)
    expect(kit.cargando).toBe(false)
  })

  it('cargarKit con error deja un mensaje legible', async () => {
    api.getKit.mockRejectedValue(new ApiError(500, 'x'))
    await cargarKit()
    expect(kit.error).not.toBe('')
    expect(kit.data).toBeNull()
  })

  it('arreglar reinstala y muestra el estado nuevo', async () => {
    kit.data = structuredClone(kitRoto)
    api.arreglarKit.mockResolvedValue({ ok: true, error: '', estado: kitOk.estado })
    await arreglar()
    expect(kit.data?.estado.al_dia).toBe(true)
    expect(kit.errorArreglo).toBe('')
    expect(kit.arreglando).toBe(false)
  })

  it('arreglar con falla muestra el error y el estado que quedó', async () => {
    kit.data = structuredClone(kitRoto)
    api.arreglarKit.mockResolvedValue({ ok: false, error: 'No pude respaldar', estado: kitRoto.estado })
    await arreglar()
    expect(kit.errorArreglo).toBe('No pude respaldar')
    expect(kit.data?.estado.al_dia).toBe(false)
  })

  it('arreglar con corte de red muestra el error', async () => {
    kit.data = structuredClone(kitRoto)
    api.arreglarKit.mockRejectedValue(new ApiError(0, 'Se cortó la conexión con el servidor'))
    await arreglar()
    expect(kit.errorArreglo).not.toBe('')
    expect(kit.arreglando).toBe(false)
  })

  it('si ya se está arreglando desde otro lado, lo dice claro', async () => {
    kit.data = structuredClone(kitRoto)
    api.arreglarKit.mockRejectedValue(new ApiError(409, 'Ya se está arreglando el kit: esperá a que termine.'))
    await arreglar()
    expect(kit.errorArreglo).toBe('Ya se está arreglando el kit: esperá a que termine y revisá de nuevo.')
    expect(kit.arreglando).toBe(false)
  })

  it('arreglar no se pisa a sí mismo', async () => {
    kit.data = structuredClone(kitRoto)
    api.arreglarKit.mockResolvedValue({ ok: true, error: '', estado: kitOk.estado })
    await Promise.all([arreglar(), arreglar()])
    expect(api.arreglarKit).toHaveBeenCalledTimes(1)
  })

  it('abrirRegla carga el texto y cerrarRegla lo saca', async () => {
    api.getRegla.mockResolvedValue('# Hola')
    await abrirRegla({ id: 'r', titulo: 'R', proposito: 'p' })
    expect(kit.regla).toMatchObject({ id: 'r', texto: '# Hola', cargando: false, error: '' })
    cerrarRegla()
    expect(kit.regla).toBeNull()
  })

  it('abrirRegla con error', async () => {
    api.getRegla.mockRejectedValue(new ApiError(404, 'No encuentro esa regla'))
    await abrirRegla({ id: 'r', titulo: 'R', proposito: 'p' })
    expect(kit.regla?.error).not.toBe('')
    expect(kit.regla?.texto).toBe('')
  })
})
