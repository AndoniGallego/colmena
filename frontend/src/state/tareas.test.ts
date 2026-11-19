// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { EVENTO_PROGRAMADAS } from '../lib/tareas'
import { ApiError } from '../api/types'
import type { Programa, Programadas } from '../api/programadasApi'
import { alternarPausa, borrar, cargarTareas, closeTareas, correr, guardar, interruptor, openTareas, resetTareas, setTareasApi, tareas, tareasOpen } from './tareas'

const prog = (o: Partial<Programa> = {}): Programa => ({ id: 'a'.repeat(32), nombre: 'T', repo: '/r', pedido: 'p', agente: 'claude', modelo: '', cuando: { tipo: 'diaria', hora: '09:00' }, pausada: true, proxima: null, ...o })
const datos = (o: Partial<Programadas> = {}): Programadas => ({ habilitado: false, programas: [prog()], cursor_disponible: false, ...o })

const api = { get: vi.fn(), historial: vi.fn(), crear: vi.fn(), editar: vi.fn(), borrar: vi.fn(), pausar: vi.fn(), correr: vi.fn(), habilitar: vi.fn() }

beforeEach(() => {
  Object.values(api).forEach((m) => m.mockReset())
  api.historial.mockResolvedValue([])
  setTareasApi(api)
  resetTareas()
})

describe('state/tareas', () => {
  it('abre y cierra con historial', () => {
    openTareas()
    expect(tareasOpen.value).toBe(true)
    expect(history.state.orqTareas).toBe(true)
    closeTareas()
  })

  it('cargarTareas trae programas e historial; un error queda visible', async () => {
    api.get.mockResolvedValue(datos())
    api.historial.mockResolvedValue([{ id: 'c1' }])
    await cargarTareas()
    expect(tareas.data?.programas).toHaveLength(1)
    expect(tareas.historial).toHaveLength(1)
    api.get.mockRejectedValue(new ApiError(500, 'x'))
    await cargarTareas()
    expect(tareas.error).not.toBe('')
  })

  it('alternarPausa invierte el estado y recarga', async () => {
    api.get.mockResolvedValue(datos())
    await cargarTareas()
    api.pausar.mockResolvedValue(prog({ pausada: false }))
    await alternarPausa(tareas.data!.programas[0])
    expect(api.pausar).toHaveBeenCalledWith('a'.repeat(32), false)
    expect(api.get).toHaveBeenCalledTimes(2)
  })

  it('correr manda un id distinto por clic y muestra el 409', async () => {
    const p = prog()
    api.correr.mockResolvedValue(undefined)
    api.get.mockResolvedValue(datos())
    await correr(p)
    await correr(p)
    expect(api.correr.mock.calls[0][1]).not.toBe(api.correr.mock.calls[1][1])
    api.correr.mockRejectedValue(new ApiError(409, 'Ya hay una corrida abierta'))
    await correr(p)
    expect(tareas.errorAccion).toBe('Ya hay una corrida abierta')
  })

  it('borrar y guardar actualizan y recargan', async () => {
    api.get.mockResolvedValue(datos())
    api.borrar.mockResolvedValue(undefined)
    await borrar(prog())
    expect(api.borrar).toHaveBeenCalledWith('a'.repeat(32))
    api.crear.mockResolvedValue(prog())
    api.editar.mockResolvedValue(prog())
    const cuerpo = { nombre: 'n', repo: '/r', pedido: 'p', agente: 'claude' as const, modelo: '', cuando: { tipo: 'diaria' as const, hora: '09:00' } }
    expect(await guardar(cuerpo)).toBe(true)
    expect(api.crear).toHaveBeenCalledWith(cuerpo)
    expect(await guardar(cuerpo, 'b'.repeat(32))).toBe(true)
    expect(api.editar).toHaveBeenCalledWith('b'.repeat(32), cuerpo)
    api.crear.mockRejectedValue(new ApiError(400, 'Esa carpeta no es la raíz de un repo de git'))
    expect(await guardar(cuerpo)).toBe(false)
    expect(tareas.errorForm).toBe('Esa carpeta no es la raíz de un repo de git')
  })

  it('interruptor: apagar no pide PIN; prender sí y maneja 403 y 429', async () => {
    api.get.mockResolvedValue(datos({ habilitado: true }))
    api.habilitar.mockResolvedValue(false)
    await interruptor(false)
    expect(api.habilitar).toHaveBeenCalledWith(false, undefined)
    api.habilitar.mockRejectedValue(new ApiError(403, 'PIN incorrecto'))
    expect(await interruptor(true, '1234')).toBe(false)
    expect(tareas.pinError).toBe('PIN incorrecto')
    api.habilitar.mockRejectedValue(new ApiError(429, 'Demasiados intentos', 30))
    await interruptor(true, '1234')
    expect(tareas.pinBloqueadoHasta).toBeGreaterThan(Date.now())
    api.habilitar.mockResolvedValue(true)
    api.get.mockResolvedValue(datos({ habilitado: true }))
    expect(await interruptor(true, '1234')).toBe(true)
    expect(tareas.pinError).toBe('')
  })

  it('el evento SSE recarga solo si la vista está abierta', async () => {
    api.get.mockResolvedValue(datos())
    window.dispatchEvent(new Event(EVENTO_PROGRAMADAS))
    expect(api.get).not.toHaveBeenCalled()
    openTareas()
    window.dispatchEvent(new Event(EVENTO_PROGRAMADAS))
    await Promise.resolve()
    expect(api.get).toHaveBeenCalledTimes(1)
    closeTareas()
  })
})
