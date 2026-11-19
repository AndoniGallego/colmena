import { describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { correrGancho, validarPiezas } from './index'

const vista = { render: () => null }
const seccion = () => ({ titulo: 'Demo', icono: 'clock' as const, vista, visible: ref(false) })

describe('registro de piezas', () => {
  it('sin piezas no hay nada que sumar', () => {
    expect(validarPiezas({})).toEqual([])
  })

  it('acepta piezas válidas en orden de carpeta', () => {
    const r = validarPiezas({ './zeta/pieza.ts': { default: { id: 'zeta' } }, './demo/pieza.ts': { default: { id: 'demo', seccion: seccion() } } })
    expect(r.map((p) => p.id)).toEqual(['demo', 'zeta'])
  })

  it('descarta y avisa las que no cumplen la forma', () => {
    const avisar = vi.fn()
    const r = validarPiezas(
      {
        './a/pieza.ts': {},
        './b/pieza.ts': { default: { id: 'Con Espacios' } },
        './c/pieza.ts': { default: { id: 'c', seccion: { titulo: 'C' } } },
        './d/pieza.ts': { default: { id: 'd', avisos: { kind: 'X!', etiqueta: 'D' } } },
        './e/pieza.ts': { default: { id: 'board' } },
        './f/pieza.ts': { default: { id: 'f', notificaciones: { pref: { key: 'asks' } } } },
        './g/pieza.ts': { default: { id: 'g' } },
      },
      avisar,
    )
    expect(r.map((p) => p.id)).toEqual(['g'])
    expect(avisar).toHaveBeenCalledTimes(6)
  })

  it('un id repetido se queda con la primera', () => {
    const avisar = vi.fn()
    const r = validarPiezas({ './a/pieza.ts': { default: { id: 'demo' } }, './b/pieza.ts': { default: { id: 'demo' } } }, avisar)
    expect(r).toHaveLength(1)
    expect(avisar).toHaveBeenCalledOnce()
  })

  it('un kind de aviso o una pref repetidos entre piezas se descartan', () => {
    const avisar = vi.fn()
    const av = (kind: string) => ({ kind, icono: 'bell', etiqueta: 'x', abierto: () => false, ir: () => {} })
    const r = validarPiezas({ './a/pieza.ts': { default: { id: 'a', avisos: av('demo') } }, './b/pieza.ts': { default: { id: 'b', avisos: av('demo') } } }, avisar)
    expect(r.map((p) => p.id)).toEqual(['a'])
  })
})

describe('ganchos de pieza aislados', () => {
  it('un gancho que tira se reporta con el id de la pieza y no corta a los demás', async () => {
    const reportar = vi.fn()
    const ok = vi.fn()
    const piezas = [
      { id: 'rota', init: () => { throw new Error('mal') } },
      { id: 'asinc', init: async () => { throw new Error('tarde') } },
      { id: 'sana', init: ok },
    ]
    for (const p of piezas) await correrGancho(p, 'init', reportar)
    expect(ok).toHaveBeenCalledOnce()
    expect(reportar).toHaveBeenCalledTimes(2)
    expect(reportar.mock.calls[0][0]).toContain('rota')
    expect(reportar.mock.calls[0][0]).toContain('init')
    expect(reportar.mock.calls[1][0]).toContain('asinc')
  })

  it('una pieza sin el gancho no hace nada', async () => {
    const reportar = vi.fn()
    await correrGancho({ id: 'x' }, 'mock', reportar)
    expect(reportar).not.toHaveBeenCalled()
  })
})
