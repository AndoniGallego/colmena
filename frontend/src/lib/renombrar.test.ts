import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { armarRenombrar, createLongPress, grupoRenombrable, pestanaActiva, pestanaRenombrable } from './renombrar'

describe('quién se puede renombrar', () => {
  it('grupos del guardián sin fijar', () => {
    expect(grupoRenombrable({ id: 'g3', pinned: false })).toBe(true)
    expect(grupoRenombrable({ id: 'g3' })).toBe(true)
  })
  it('no los fijados ni los que no son del guardián', () => {
    expect(grupoRenombrable({ id: 'g3', pinned: true })).toBe(false)
    expect(grupoRenombrable({ id: 'w1' })).toBe(false)
    expect(grupoRenombrable({ id: 'g3:t1' })).toBe(false)
  })
  it('pestañas g1:t2 de un grupo renombrable', () => {
    expect(pestanaRenombrable({ id: 'g1' }, { id: 'g1:t2' })).toBe(true)
    expect(pestanaRenombrable({ id: 'g1', pinned: true }, { id: 'g1:t2' })).toBe(false)
    expect(pestanaRenombrable({ id: 'w1' }, { id: 'w1:2' })).toBe(false)
  })
})

describe('armarRenombrar', () => {
  it('arma el pedido con el nombre recortado', () => {
    expect(armarRenombrar('grupo', 'g1', '  Nuevo  ', 'Viejo')).toEqual({ tipo: 'grupo', id: 'g1', nombre: 'Nuevo' })
  })
  it('null si queda vacío o no cambió', () => {
    expect(armarRenombrar('grupo', 'g1', '   ', 'Viejo')).toBeNull()
    expect(armarRenombrar('pestana', 'g1:t1', 'Viejo ', 'Viejo')).toBeNull()
  })
  it('corta a 60 caracteres', () => {
    expect(armarRenombrar('grupo', 'g1', 'x'.repeat(80), 'a')!.nombre).toHaveLength(60)
  })
})

describe('createLongPress', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())
  it('dispara tras mantener ~500ms', () => {
    const done = vi.fn()
    const lp = createLongPress(done)
    lp.down(10, 10)
    vi.advanceTimersByTime(499)
    expect(done).not.toHaveBeenCalled()
    vi.advanceTimersByTime(2)
    expect(done).toHaveBeenCalledTimes(1)
  })
  it('soltar antes cancela', () => {
    const done = vi.fn()
    const lp = createLongPress(done)
    lp.down(0, 0)
    vi.advanceTimersByTime(200)
    lp.cancel()
    vi.advanceTimersByTime(1000)
    expect(done).not.toHaveBeenCalled()
  })
  it('moverse más del umbral cancela, un temblor chico no', () => {
    const done = vi.fn()
    const lp = createLongPress(done)
    lp.down(0, 0)
    lp.move(3, 3)
    vi.advanceTimersByTime(600)
    expect(done).toHaveBeenCalledTimes(1)
    lp.down(0, 0)
    lp.move(30, 0)
    vi.advanceTimersByTime(600)
    expect(done).toHaveBeenCalledTimes(1)
  })
})

describe('pestanaActiva', () => {
  const tabs = [{ id: 'g1:t1' }, { id: 'g1:t2' }, { id: 'g1:t3' }]
  it('prefiere la que tiene la sesión abierta, luego la enfocada, luego la primera', () => {
    expect(pestanaActiva(tabs, 'g1:t3', 'g1:t2')?.id).toBe('g1:t3')
    expect(pestanaActiva(tabs, null, 'g1:t2')?.id).toBe('g1:t2')
    expect(pestanaActiva(tabs, null, 'otra')?.id).toBe('g1:t1')
  })
  it('null si no hay pestañas', () => {
    expect(pestanaActiva([], null, null)).toBeNull()
  })
})
