import { describe, expect, it } from 'vitest'
import type { LimpiezaItem, LimpiezaPreviewItem } from '../api/types'
import { agrupar, clampDias, chipLabel, itemKey, marcasIniciales, motivoRevision, parseLimpiar, razonLabel } from './limpieza'

const item = (id: string, over: Partial<LimpiezaItem> = {}): LimpiezaItem => ({
  tipo: 'tab',
  target_id: id,
  workspace: 'ws',
  label: id,
  razones: [{ tipo: 'quieto', dias: 8 }],
  sesiones: [],
  terminales: 1,
  marcado: true,
  bloqueado: null,
  ...over,
})
const prev = (over: Partial<LimpiezaPreviewItem> = {}): LimpiezaPreviewItem => ({ tipo: 'tab', target_id: 'a', preview: null, error: '', bloqueantes: [], ...over })

describe('limpieza lib', () => {
  it('clamps days to 1..30', () => {
    expect(clampDias(0)).toBe(1)
    expect(clampDias(99)).toBe(30)
    expect(clampDias(7.4)).toBe(7)
    expect(clampDias(NaN)).toBe(1)
  })
  it('labels reasons and chip', () => {
    expect(razonLabel({ tipo: 'quieto', dias: 1 })).toBe('quieta hace 1 día')
    expect(razonLabel({ tipo: 'mergeada', rama: 'feature/X', base: 'origin/main' })).toContain('feature/X')
    expect(chipLabel(1)).toBe('1 sesión quieta')
    expect(chipLabel(4)).toBe('4 sesiones quietas')
  })
  it('groups by workspace and keeps blocked rows apart without selection', () => {
    const g = agrupar([item('a'), item('b', { workspace: 'otro' }), item('c', { bloqueado: 'corriendo' }), item('d')])
    expect(g.grupos.map((x) => [x.workspace, x.items.map((i) => i.target_id)])).toEqual([['ws', ['a', 'd']], ['otro', ['b']]])
    expect(g.bloqueados.map((i) => i.target_id)).toEqual(['c'])
  })
  it('initial marks skip blocked rows and honor a preselection of known ids only', () => {
    const items = [item('a'), item('b', { marcado: false }), item('c', { bloqueado: 'sin_leer', marcado: false })]
    expect(marcasIniciales(items)).toEqual({ 'tab:a': true, 'tab:b': false })
    expect(marcasIniciales(items, ['b', 'c', 'zzz'])).toEqual({ 'tab:a': false, 'tab:b': true })
    expect(itemKey(items[0])).toBe('tab:a')
  })
  it('review reasons for rows the server will not close', () => {
    expect(motivoRevision(prev({ bloqueantes: [{ pane_id: 'p', status: 'working' }] }))).toBe('Está trabajando')
    expect(motivoRevision(prev({ bloqueantes: [{ pane_id: 'p', status: 'unknown' }] }))).toBe('No sé si está trabajando')
    expect(motivoRevision(prev({ error: 'Cambió: algo' }))).toBe('Cambió')
    expect(motivoRevision(prev({ error: 'Ya no está abierto' }))).toBe('Ya no está')
    expect(motivoRevision(prev())).toBe('Cambió')
  })
  it('parses the limpieza block from Centinela, dedupes and caps ids', () => {
    const ids = Array.from({ length: 20 }, (_, i) => `w${i}:t1`)
    const text = 'Mirá:\n```limpieza\n' + JSON.stringify({ preseleccion: ['w1:t1', 'w1:t1', '../x', 5, ...ids] }) + '\n```\nlisto'
    const p = parseLimpiar(text)
    expect(p.limpiar?.preseleccion.length).toBe(12)
    expect(p.limpiar?.preseleccion).not.toContain('../x')
    expect(p.before).toContain('Mirá')
    expect(parseLimpiar('```limpieza\n{"x":1}\n```').limpiar).toBeNull()
  })
})
