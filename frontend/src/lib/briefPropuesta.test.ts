import { describe, expect, it } from 'vitest'
import { MAX_TAREA } from './nuevaTerminal'
import { briefPropuesta } from './briefPropuesta'

const base = { id: 'aaaaaaaaaaaa', texto: 'El error boom se repitió 24 veces' }

describe('briefPropuesta', () => {
  it('lleva el texto, la semana, la métrica y el pedido de diseño y plan, en orden', () => {
    const b = briefPropuesta({ ...base, metrica: { nombre: 'veces', valor: 24 } }, '2026-W47')
    expect(b.split('\n').filter(Boolean)).toEqual([
      'Propuesta del resumen de la semana 2026-W47: El error boom se repitió 24 veces',
      'Métrica: veces = 24',
      'Armar diseño y plan antes de tocar código; no cambiar nada sin mi OK.',
    ])
  })

  it('sin métrica omite la línea', () => {
    const b = briefPropuesta(base, '2026-W47')
    expect(b).not.toContain('Métrica')
    expect(b).toContain('Armar diseño y plan')
  })

  it('con valor nulo dice sin dato', () => {
    const b = briefPropuesta({ ...base, metrica: { nombre: 'veces', valor: null as never } }, '2026-W47')
    expect(b).toContain('Métrica: veces = sin dato')
  })

  it('con un texto de 5000 no pasa del tope y conserva el pedido final', () => {
    const b = briefPropuesta({ ...base, texto: 'x'.repeat(5000) }, '2026-W47')
    expect(b.length).toBeLessThanOrEqual(MAX_TAREA)
    expect(b).toContain('Armar diseño y plan')
  })
})
