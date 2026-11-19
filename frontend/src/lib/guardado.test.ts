import { describe, expect, it } from 'vitest'
import { normalizeGuardado } from '../api/normalize'
import { guardadoLabel, leyenda, paneEstadoLabel, puedeEsperarMas } from './guardado'

const raw = (over: Record<string, unknown> = {}) => ({
  id: 'lote-aaaa-0001',
  origen: 'plan',
  plan_id: 'plan-aaaa-0001',
  vencido: false,
  puede_cerrar_igual: false,
  terminado: false,
  targets: [{ key: 'p1', tipo: 'tab', target_id: 'w1:t1', label: 'Uno', estado: 'guardando', error: '', guardado: '', panes: [{ pane_id: 'w1:p1', titulo: 'a', estado: 'bloqueado' }] }],
  ...over,
})

describe('guardado', () => {
  it('normalizes the lote and ignores garbage', () => {
    const g = normalizeGuardado(raw())!
    expect(g.targets[0].panes[0].estado).toBe('bloqueado')
    expect(normalizeGuardado({ id: 3 })).toBeNull()
    expect(normalizeGuardado(raw({ targets: [{ estado: 'raro', panes: [{ estado: 'x' }] }] }))!.targets[0].estado).toBe('guardando')
  })

  it('says what is going on in plain words', () => {
    expect(leyenda(normalizeGuardado(raw())!)).toContain('esper')
    expect(leyenda(normalizeGuardado(raw({ vencido: true }))!)).toContain('No cierro solo')
    expect(leyenda(normalizeGuardado(raw({ terminado: true }))!)).toBe('Listo')
    expect(paneEstadoLabel('bloqueado')).toBe('esperando tu respuesta')
    expect(guardadoLabel('vencido')).toBe('cerrado sin esperar')
  })

  it('only offers Esperar más after the 5 minutes', () => {
    expect(puedeEsperarMas(normalizeGuardado(raw())!)).toBe(false)
    expect(puedeEsperarMas(normalizeGuardado(raw({ vencido: true }))!)).toBe(true)
  })
})
