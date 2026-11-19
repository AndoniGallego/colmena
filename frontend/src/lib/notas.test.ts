import { describe, expect, it } from 'vitest'
import type { Nota } from '../api/types'
import { contarPendientes, filtrarNotas, notaDeMensaje, notasNotch } from './notas'

function nota(id: string, p: Partial<Nota> = {}): Nota {
  return { id, tipo: 'recordatorio', texto: id, hecha_at: null, creada_at: '2026-11-18T10:00:00Z', editada_at: '2026-11-18T10:00:00Z', origen: null, ...p }
}

const lista = [
  nota('a'),
  nota('b', { hecha_at: '2026-11-18T11:00:00Z' }),
  nota('c', { tipo: 'apunte' }),
]

describe('filtrarNotas', () => {
  it('para-hacer: recordatorios sin hecha', () => {
    expect(filtrarNotas(lista, 'para-hacer').map((n) => n.id)).toEqual(['a'])
  })
  it('hechas: recordatorios con hecha', () => {
    expect(filtrarNotas(lista, 'hechas').map((n) => n.id)).toEqual(['b'])
  })
  it('apuntes: solo apuntes', () => {
    expect(filtrarNotas(lista, 'apuntes').map((n) => n.id)).toEqual(['c'])
  })
  it('todas: todo, en el orden recibido', () => {
    expect(filtrarNotas(lista, 'todas').map((n) => n.id)).toEqual(['a', 'b', 'c'])
  })
})

describe('contarPendientes', () => {
  it('ignora apuntes y hechas', () => {
    expect(contarPendientes(lista)).toBe(1)
  })
})

describe('notasNotch', () => {
  it('devuelve todas las no hechas, las más nuevas primero', () => {
    const l = Array.from({ length: 9 }, (_, i) => nota(`n${i}`, { creada_at: `2026-11-18T10:0${i}:00Z` }))
    l.push(nota('hecha', { hecha_at: '2026-11-18T12:00:00Z', creada_at: '2026-11-18T13:00:00Z' }))
    l.push(nota('ap', { tipo: 'apunte', creada_at: '2026-11-18T14:00:00Z' }))
    expect(notasNotch(l).map((n) => n.id)).toEqual(['ap', 'n8', 'n7', 'n6', 'n5', 'n4', 'n3', 'n2', 'n1', 'n0'])
  })
})

describe('notaDeMensaje', () => {
  const o = nota('o', { origen: { sid: 's1', nombre: 'x', ts: 't1' } })
  it('encuentra por sid y ts', () => {
    expect(notaDeMensaje([lista[0], o], 's1', 't1')).toBe(o)
  })
  it('ts vacío da undefined', () => {
    expect(notaDeMensaje([nota('z', { origen: { sid: 's1', nombre: 'x', ts: '' } })], 's1', '')).toBeUndefined()
  })
})

describe('recortarNota y corto', () => {
  it('recortarNota deja el texto corto igual y el largo en el tope con "…"', async () => {
    const { recortarNota, corto } = await import('./notas')
    expect(recortarNota('hola')).toEqual({ texto: 'hola', recortado: false })
    const r = recortarNota('a'.repeat(4001))
    expect([...r.texto]).toHaveLength(4000)
    expect(r.recortado).toBe(true)
    expect(corto('abc', 10)).toBe('abc')
    expect([...corto('a'.repeat(500))].length).toBeLessThanOrEqual(140)
  })
})
