import { effectScope, nextTick, shallowRef } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Nota } from '../api/types'
import { DESHACER_MS, ERR_DESHACER, ERR_HECHA, useCompletarNotas } from './useCompletarNotas'

function nota(i: number, tipo: Nota['tipo'] = 'recordatorio'): Nota {
  return {
    id: `n${i}`,
    tipo,
    texto: `Nota ${i}`,
    hecha_at: null,
    creada_at: `2026-11-18T10:00:${String(i).padStart(2, '0')}Z`,
    editada_at: `2026-11-18T10:00:${String(i).padStart(2, '0')}Z`,
    origen: null,
  }
}

const flush = async () => {
  for (let i = 0; i < 5; i++) await Promise.resolve()
  await nextTick()
}

function montar(inicial: Nota[], tope = 4) {
  const base = shallowRef<Nota[]>(inicial)
  const marcar = vi.fn(async (_id: string, _hecha: boolean) => undefined as void)
  const scope = effectScope()
  const c = scope.run(() => useCompletarNotas({ base: () => base.value, marcar, tope }))!
  return { c, base, marcar, scope, ids: () => c.visibles.value.map((n) => n.id) }
}

/** Promesa que se resuelve a mano: un pedido "en vuelo". */
function enVuelo() {
  let fin!: () => void
  const p = new Promise<void>((r) => (fin = () => r()))
  return { p, fin }
}

describe('useCompletarNotas', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('muestra como mucho el tope', () => {
    const { ids } = montar(Array.from({ length: 9 }, (_, i) => nota(i)))
    expect(ids()).toEqual(['n0', 'n1', 'n2', 'n3'])
  })

  it('al marcar una con la lista llena sigue en su lugar y no pasa del tope', async () => {
    const t = montar(Array.from({ length: 9 }, (_, i) => nota(i)))
    await t.c.completar(nota(1))
    t.base.value = t.base.value.filter((n) => n.id !== 'n1')
    await flush()
    expect(t.ids()).toEqual(['n0', 'n1', 'n2', 'n3'])
    expect(t.c.esHecha('n1')).toBe(true)
  })

  it('marcar llama marcar(id, true), queda hecha con Deshacer 5 s y después se va', async () => {
    const t = montar([nota(1)])
    await t.c.completar(nota(1))
    expect(t.marcar).toHaveBeenCalledTimes(1)
    expect(t.marcar).toHaveBeenCalledWith('n1', true)
    expect(t.c.esHecha('n1')).toBe(true)
    t.base.value = []
    await flush()
    expect(t.ids()).toEqual(['n1'])
    vi.advanceTimersByTime(DESHACER_MS)
    await flush()
    expect(t.c.esHecha('n1')).toBe(false)
    expect(t.ids()).toEqual([])
  })

  it('Deshacer llama marcar(id, false) una sola vez aunque se toque dos veces', async () => {
    const t = montar([nota(1)])
    await t.c.completar(nota(1))
    t.base.value = []
    void t.c.deshacer('n1')
    void t.c.deshacer('n1')
    await flush()
    expect(t.marcar.mock.calls.filter((c) => c[1] === false)).toHaveLength(1)
    expect(t.marcar).toHaveBeenLastCalledWith('n1', false)
    expect(t.c.esHecha('n1')).toBe(false)
  })

  it('Deshacer tocado mientras marcar(true) está en vuelo se aplica al terminar, una sola vez', async () => {
    const t = montar([nota(1)])
    const v = enVuelo()
    t.marcar.mockImplementationOnce(() => v.p)
    const pedido = t.c.completar(nota(1))
    void t.c.deshacer('n1')
    void t.c.deshacer('n1')
    expect(t.marcar).toHaveBeenCalledTimes(1)
    v.fin()
    await pedido
    await flush()
    expect(t.marcar.mock.calls.filter((c) => c[1] === false)).toHaveLength(1)
    expect(t.marcar).toHaveBeenLastCalledWith('n1', false)
    vi.advanceTimersByTime(DESHACER_MS)
    await flush()
    expect(t.c.esHecha('n1')).toBe(false)
  })

  it('un segundo completar con el pedido abierto no manda otro marcar', async () => {
    const t = montar([nota(1)])
    const v = enVuelo()
    t.marcar.mockImplementationOnce(() => v.p)
    const pedido = t.c.completar(nota(1))
    void t.c.completar(nota(1))
    expect(t.marcar).toHaveBeenCalledTimes(1)
    v.fin()
    await pedido
    expect(t.marcar).toHaveBeenCalledTimes(1)
  })

  it('un segundo Deshacer mientras el primero sigue en vuelo no manda otro pedido', async () => {
    const t = montar([nota(1)])
    await t.c.completar(nota(1))
    const v = enVuelo()
    t.marcar.mockImplementationOnce(() => v.p)
    const pedido = t.c.deshacer('n1')
    void t.c.deshacer('n1')
    expect(t.marcar.mock.calls.filter((c) => c[1] === false)).toHaveLength(1)
    v.fin()
    await pedido
    expect(t.marcar.mock.calls.filter((c) => c[1] === false)).toHaveLength(1)
  })

  it('tras un doble Deshacer, volver a completar la nota no se deshace sola', async () => {
    const t = montar([nota(1)])
    await t.c.completar(nota(1))
    const v = enVuelo()
    t.marcar.mockImplementationOnce(() => v.p)
    const pedido = t.c.deshacer('n1')
    void t.c.deshacer('n1')
    v.fin()
    await pedido
    await t.c.completar(nota(1))
    await flush()
    expect(t.marcar.mock.calls.map((c) => c[1])).toEqual([true, false, true])
    expect(t.c.esHecha('n1')).toBe(true)
  })

  it('si falla marcar avisa en castellano y la nota vuelve', async () => {
    const t = montar([nota(1)])
    t.marcar.mockRejectedValueOnce(new Error('boom'))
    await t.c.completar(nota(1))
    expect(t.c.error.value).toBe(ERR_HECHA)
    expect(t.c.esHecha('n1')).toBe(false)
    expect(t.ids()).toEqual(['n1'])
  })

  it('si falla Deshacer avisa y la nota sigue hecha hasta que vence', async () => {
    const t = montar([nota(1)])
    await t.c.completar(nota(1))
    t.marcar.mockRejectedValueOnce(new Error('boom'))
    await t.c.deshacer('n1')
    expect(t.c.error.value).toBe(ERR_DESHACER)
    expect(t.c.esHecha('n1')).toBe(true)
    vi.advanceTimersByTime(DESHACER_MS)
    expect(t.c.esHecha('n1')).toBe(false)
  })

  it('al cerrar el alcance no queda ningún timer vivo', async () => {
    const t = montar([nota(1)])
    await t.c.completar(nota(1))
    expect(vi.getTimerCount()).toBe(1)
    t.scope.stop()
    expect(vi.getTimerCount()).toBe(0)
  })
})
