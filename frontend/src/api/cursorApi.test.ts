import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './types'
import { getCursorEstado, getLog, getTrabajadores, normalizarTrabajador, postCancelar } from './cursorApi'

const TID = 'a'.repeat(32)
const crudo = {
  id: TID,
  nombre: 'Renombrar helpers',
  estado: 'ok',
  ruta: '/home/u/proy-cursor-x',
  rama: 'cursor/x-ab12',
  base: '0123456789abcdef',
  inicio: 1_800_000_000,
  fin: 1_800_000_125,
  codigo: 0,
  archivos: ['a.py', 3, 'b.py'],
  resumen: 'Hice algo',
  pedido: 'Renombrá',
  origen: { tipo: 'claude', nombre: 'Tienda' },
  log_recortado: false,
}

const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status })

describe('cursorApi', () => {
  it('normaliza un trabajador y descarta basura', () => {
    const t = normalizarTrabajador(crudo)!
    expect(t.id).toBe(TID)
    expect(t.estado).toBe('ok')
    expect(t.archivos).toEqual(['a.py', 'b.py'])
    expect(t.origen).toEqual({ tipo: 'claude', nombre: 'Tienda' })
    expect(normalizarTrabajador({ ...crudo, id: 'x' })).toBeNull()
    expect(normalizarTrabajador({ ...crudo, estado: 'raro' })).toBeNull()
    expect(normalizarTrabajador(null)).toBeNull()
  })

  it('getTrabajadores y getCursorEstado', async () => {
    const f = vi.fn().mockResolvedValueOnce(json({ trabajadores: [crudo, { id: 'malo' }] }))
      .mockResolvedValueOnce(json({ disponible: true, corriendo: 1, max_simultaneos: 2 }))
    const lista = await getTrabajadores(f as unknown as typeof fetch)
    expect(f.mock.calls[0][0]).toBe('/api/cursor/trabajadores')
    expect(lista).toHaveLength(1)
    expect(await getCursorEstado(f as unknown as typeof fetch)).toEqual({ disponible: true, corriendo: 1, max_simultaneos: 2 })
  })

  it('getLog valida el id antes de pedir', async () => {
    const f = vi.fn().mockResolvedValue(json({ texto: 'línea' }))
    expect(await getLog(TID, f as unknown as typeof fetch)).toBe('línea')
    expect(f.mock.calls[0][0]).toBe(`/api/cursor/trabajadores/${TID}/log`)
    await expect(getLog('../x', f as unknown as typeof fetch)).rejects.toBeInstanceOf(ApiError)
    expect(f).toHaveBeenCalledTimes(1)
  })

  it('postCancelar hace POST y un 409 es ApiError con el detalle', async () => {
    const f = vi.fn().mockResolvedValueOnce(json({ ok: true }))
      .mockResolvedValueOnce(json({ detail: 'el trabajador ya no está corriendo' }, 409))
    await postCancelar(TID, f as unknown as typeof fetch)
    expect(f.mock.calls[0][0]).toBe(`/api/cursor/trabajadores/${TID}/cancelar`)
    expect(f.mock.calls[0][1]).toEqual(expect.objectContaining({ method: 'POST', credentials: 'same-origin' }))
    await expect(postCancelar(TID, f as unknown as typeof fetch)).rejects.toMatchObject({
      status: 409,
      message: 'el trabajador ya no está corriendo',
    })
  })
})
