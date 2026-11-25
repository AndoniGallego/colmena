import { describe, expect, it } from 'vitest'
import { normalizeBoard, normalizeAvisos } from '../api/normalize'
import { AVISO_ICON, AVISO_TIPO } from './avisos'
import { DEFAULT_PREFS } from './push'
import { rotuloTraba, normalizeTraba } from './trabas'

const NOW = Date.parse('2026-11-04T12:10:00Z')
const desde = (min: number) => (NOW - min * 60_000) / 1000

describe('rotuloTraba', () => {
  it('dice el tipo en simple y desde cuándo', () => {
    expect(rotuloTraba({ tipo: 'repetida', desde: desde(4), detalle: 'x' }, NOW)).toBe('Repite lo mismo · hace 4 min')
    expect(rotuloTraba({ tipo: 'fallando', desde: desde(12), detalle: 'x' }, NOW)).toBe('Falla una y otra vez · hace 12 min')
    expect(rotuloTraba({ tipo: 'colgada', desde: desde(5), detalle: 'x' }, NOW)).toBe('Herramienta colgada · hace 5 min')
    expect(rotuloTraba({ tipo: 'quieta', desde: desde(11), detalle: 'x' }, NOW)).toBe('Sin actividad · hace 11 min')
  })
})

describe('normalizeTraba', () => {
  it('descarta lo que no es una traba conocida', () => {
    expect(normalizeTraba(null)).toBeUndefined()
    expect(normalizeTraba({ tipo: 'rara', desde: 1, detalle: 'x' })).toBeUndefined()
    expect(normalizeTraba({ tipo: 'quieta', desde: 'a', detalle: 'x' })).toEqual({ tipo: 'quieta', desde: 0, detalle: 'x' })
    expect(normalizeTraba({ tipo: 'repetida', desde: 5, detalle: 'y'.repeat(300) })?.detalle).toHaveLength(160)
  })

  it('el tablero conserva la traba de la tarjeta y no inventa una', () => {
    const board = normalizeBoard({
      workspaces: [{ id: 'w1', tabs: [{ id: 't1', agents: [
        { pane_id: 'w1:p1', status: 'working', traba: { tipo: 'repetida', desde: 3, detalle: 'Grep repetido' } },
        { pane_id: 'w1:p2', status: 'working' },
      ] }] }],
    })
    const agents = board.workspaces[0].tabs[0].agents
    expect(agents[0].traba).toEqual({ tipo: 'repetida', desde: 3, detalle: 'Grep repetido' })
    expect(agents[1].traba).toBeUndefined()
  })
})

describe('aviso trabada', () => {
  it('tiene ícono, rótulo, preferencia prendida y pasa la normalización', () => {
    expect(AVISO_ICON.trabada).toBe('warn')
    expect(AVISO_TIPO.trabada).toBe('Trabada')
    expect(DEFAULT_PREFS.trabada).toBe(true)
    const out = normalizeAvisos({ items: [{ id: 1, ts: 1, kind: 'trabada', titulo: 'Uno parece trabada', cuerpo: 'x' }] })
    expect(out.items[0].kind).toBe('trabada')
  })
})
