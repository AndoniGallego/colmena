import { describe, expect, it } from 'vitest'
import type { Subagente } from '../api/types'
import { normalizeSubagentes } from '../api/normalize'
import { anyWorking, elapsed, heading, latest, shown, stepOf } from './subagentes'

const mk = (id: string, estado: Subagente['estado']): Subagente => ({ id, descripcion: id, tipo: '', modelo: '', estado, inicio: '', segundos: 0, paso: '', tokens: null })

describe('subagentes', () => {
  it('formatea el tiempo', () => {
    expect(elapsed(7)).toBe('7 s')
    expect(elapsed(125)).toBe('2 min')
    expect(elapsed(3600)).toBe('1 h')
    expect(elapsed(3900)).toBe('1 h 5 min')
  })
  it('arma el encabezado', () => {
    expect(heading([mk('a', 'trabajando'), mk('b', 'trabajando'), mk('c', 'termino')])).toBe('2 agentes trabajando')
    expect(heading([mk('a', 'trabajando')])).toBe('1 agente trabajando')
    expect(heading([mk('c', 'termino')])).toBe('1 agente terminó')
    expect(heading([mk('c', 'termino'), mk('d', 'termino')])).toBe('2 agentes terminaron')
    expect(heading([mk('c', 'termino'), mk('d', 'sin_actividad')])).toBe('2 agentes sin actividad')
  })
  it('elige el agente más reciente que trabaja', () => {
    const a = { ...mk('a', 'trabajando'), segundos: 90, paso: 'Leyendo' }
    const b = { ...mk('b', 'trabajando'), segundos: 12, paso: 'Corriendo pruebas' }
    const c = { ...mk('c', 'termino'), segundos: 1 }
    expect(latest([a, b, c])?.id).toBe('b')
    expect(latest([c, mk('d', 'termino')])?.id).toBe('c')
    expect(latest([])).toBeNull()
    expect(stepOf(b)).toBe('Corriendo pruebas')
    expect(stepOf(mk('x', 'sin_actividad'))).toBe('Sin actividad hace un rato')
  })
  it('muestra como mucho 5 salvo ver todos', () => {
    const l = Array.from({ length: 8 }, (_, i) => mk(String(i), 'termino'))
    expect(shown(l, false)).toHaveLength(5)
    expect(shown(l, true)).toHaveLength(8)
    expect(anyWorking(l)).toBe(false)
  })
  it('normaliza datos raros', () => {
    const out = normalizeSubagentes({ items: [{ id: 'x', estado: 'rarisimo', segundos: -3, tokens: null }, { nada: 1 }, null] })
    expect(out).toEqual([{ id: 'x', descripcion: 'Subagente', tipo: '', modelo: '', estado: 'sin_actividad', inicio: '', segundos: 0, paso: '', tokens: null }])
    expect(normalizeSubagentes(null)).toEqual([])
  })
})
