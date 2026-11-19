import { describe, expect, it } from 'vitest'
import type { Aviso } from '../api/types'
import { AVISO_ICON, AVISO_TIPO, agruparAvisos, coincideAviso, destinoDeAviso, etiquetaAviso, etiquetaDia, horaDeAviso, iconoAviso, mezclarAvisos, tagsCerrables } from './avisos'

const at = (y: number, m: number, d: number, h = 12, min = 0) => Math.floor(new Date(y, m - 1, d, h, min).getTime() / 1000)
const av = (id: number, ts: number, over: Partial<Aviso> = {}): Aviso => ({
  id, ts, kind: 'done', titulo: 't', cuerpo: '', session_id: '', pane_id: '', fecha: '', mr: '', tag: '', entregado: true, leido: false, motivo: '', ...over,
})

describe('avisos', () => {
  it('etiqueta Hoy, Ayer o la fecha', () => {
    expect(etiquetaDia('2026-11-01', '2026-11-01')).toBe('Hoy')
    expect(etiquetaDia('2026-10-31', '2026-11-01')).toBe('Ayer')
    expect(etiquetaDia('2026-10-28', '2026-11-01')).toBe('Miércoles 28 de octubre')
  })

  it('agrupa por día local sin reordenar', () => {
    const items = [av(4, at(2026, 11, 1, 10)), av(3, at(2026, 11, 1, 9)), av(2, at(2026, 10, 31, 23, 50)), av(1, at(2026, 10, 28))]
    const g = agruparAvisos(items, '2026-11-01')
    expect(g.map((x) => [x.label, x.items.map((i) => i.id)])).toEqual([['Hoy', [4, 3]], ['Ayer', [2]], ['Miércoles 28 de octubre', [1]]])
  })

  it('hora con ceros', () => {
    expect(horaDeAviso(at(2026, 11, 1, 9, 5))).toBe('09:05')
  })

  it('el destino sigue a la notificación', () => {
    expect(destinoDeAviso(av(1, 1, { kind: 'asks', session_id: 's1' }))).toEqual({ tipo: 'sesion', id: 's1' })
    expect(destinoDeAviso(av(1, 1, { kind: 'terminal', pane_id: 'w:p1' }))).toEqual({ tipo: 'terminal', id: 'w:p1' })
    expect(destinoDeAviso(av(1, 1, { kind: 'test' }))).toEqual({ tipo: 'ninguno' })
    expect(destinoDeAviso(av(1, 1, { kind: 'mr', mr: '101:412' }))).toEqual({ tipo: 'mr', ref: '101:412' })
    expect(destinoDeAviso(av(1, 1, { kind: 'mr', mr: '101:4;12' }))).toEqual({ tipo: 'ninguno' })
    expect(destinoDeAviso(av(1, 1, { kind: 'done' }))).toEqual({ tipo: 'ninguno' })
    expect(destinoDeAviso(av(1, 1, { kind: 'cierre' }))).toEqual({ tipo: 'tablero' })
    expect(destinoDeAviso(av(1, 1, { kind: 'encadenar' }))).toEqual({ tipo: 'tablero' })
    expect(destinoDeAviso(av(1, 1, { kind: 'vigia' }))).toEqual({ tipo: 'tablero' })
  })

  it('un kind de pieza lleva a su pieza solo si está registrada', () => {
    expect(destinoDeAviso(av(1, 1, { kind: 'demo', fecha: '2026-10-28' }), ['demo'])).toEqual({ tipo: 'pieza', kind: 'demo' })
    expect(destinoDeAviso(av(1, 1, { kind: 'demo' }))).toEqual({ tipo: 'ninguno' })
  })

  it('ícono y etiqueta de un kind de pieza salen de la pieza', () => {
    const piezas = [{ kind: 'demo', icono: 'calendar' as const, etiqueta: 'Demo' }]
    expect(iconoAviso('demo', piezas)).toBe('calendar')
    expect(etiquetaAviso('demo', piezas)).toBe('Demo')
    expect(iconoAviso('demo')).toBe('bell')
    expect(etiquetaAviso('demo')).toBe('')
    expect(iconoAviso('asks', piezas)).toBe('ask')
    expect(etiquetaAviso('cierre')).toBe('Cierre del día')
  })

  it('progreso tiene ícono y etiqueta', () => {
    expect(AVISO_ICON.progreso).toBe('bell')
    expect(AVISO_TIPO.progreso).toBe('Avance')
  })

  it('mezcla sin duplicar y deja lo más nuevo primero', () => {
    const out = mezclarAvisos([av(1, 1), av(2, 2)], [av(3, 3), av(2, 2, { titulo: 'nuevo' })])
    expect(out.map((a) => a.id)).toEqual([3, 2, 1])
    expect(out[1].titulo).toBe('nuevo')
  })
})

describe('tagsCerrables', () => {
  it('solo tags leídos sin otro aviso sin leer con el mismo tag', () => {
    const items = [
      av(1, 1, { tag: 'a', leido: true }),
      av(2, 2, { tag: 'b', leido: false }),
      av(3, 3, { tag: 'c', leido: true }),
      av(4, 4, { tag: 'c', leido: false }),
    ]
    expect(tagsCerrables(items, 0)).toEqual(['a'])
  })

  it('cuenta leidosHasta y descarta tags vacíos', () => {
    const items = [av(1, 1, { tag: '' }), av(2, 2, { tag: 'x' }), av(3, 3, { tag: 'y' })]
    expect(tagsCerrables(items, 2)).toEqual(['x'])
    expect(tagsCerrables(items, 99)).toEqual(['x', 'y'])
  })
})

describe('coincideAviso', () => {
  const a = { id: 1, ts: 1, kind: 'done', titulo: '', cuerpo: '', session_id: 'abc', pane_id: '', fecha: '', mr: '', tag: '', entregado: true, leido: false, motivo: '' } as const
  it('compara por sesión, terminal o tipo y nunca por vacío', () => {
    expect(coincideAviso(a, { session_id: 'abc' })).toBe(true)
    expect(coincideAviso(a, { session_id: 'x' })).toBe(false)
    const m = av(2, 1, { kind: 'mr', mr: '7:3' })
    expect(coincideAviso(m, { mr: '7:3' })).toBe(true)
    expect(coincideAviso(m, { mr: '7:4' })).toBe(false)
    expect(coincideAviso(a, { mr: '7:3' })).toBe(false)
    expect(coincideAviso(a, { pane_id: '' })).toBe(false)
    expect(coincideAviso({ ...a, pane_id: 'p1' }, { pane_id: 'p1' })).toBe(true)
    expect(coincideAviso(a, { kind: 'demo' })).toBe(false)
    expect(coincideAviso({ ...a, kind: 'demo' }, { kind: 'demo' })).toBe(true)
  })
})
