import { describe, expect, it } from 'vitest'
import { elegidosDesdeReviewers, reviewersParaGuardar } from './mrReviewers'

const equipo = [
  { username: 'a', nombre: 'A' },
  { username: 'b', nombre: 'B' },
]

describe('mrReviewers', () => {
  it('no permite guardar sin equipo cargado', () => {
    expect(reviewersParaGuardar([], new Set(['a']), false)).toBeNull()
    expect(reviewersParaGuardar([], new Set(['a']), true)).toBeNull()
  })

  it('filtra elegidos al equipo conocido', () => {
    expect(reviewersParaGuardar(equipo, new Set(['a', 'z']), true)).toEqual(['a'])
    expect(elegidosDesdeReviewers([{ username: 'a' }, { username: 'z' }], equipo)).toEqual(new Set(['a']))
  })

  it('permite vaciar reviewers si el equipo está cargado', () => {
    expect(reviewersParaGuardar(equipo, new Set(), true)).toEqual([])
  })
})
