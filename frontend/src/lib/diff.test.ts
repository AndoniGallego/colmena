import { describe, expect, it } from 'vitest'
import { parseDiff } from './diff'

describe('parseDiff', () => {
  it('numera las líneas desde el encabezado del bloque', () => {
    const l = parseDiff('@@ -3,2 +10,3 @@ fn\n ctx\n-viejo\n+nuevo\n+otro')
    expect(l.map((x) => [x.k, x.a, x.b])).toEqual([
      ['hunk', null, null],
      ['ctx', 3, 10],
      ['del', 4, null],
      ['add', null, 11],
      ['add', null, 12],
    ])
    expect(l[2].t).toBe('viejo')
    expect(l[1].t).toBe('ctx')
  })

  it('reinicia la cuenta en cada bloque y ignora "\\ No newline"', () => {
    const l = parseDiff('@@ -1 +1 @@\n-a\n+b\n\\ No newline at end of file\n@@ -20,1 +20,1 @@\n x')
    expect(l.filter((x) => x.k !== 'hunk').map((x) => [x.a, x.b])).toEqual([[1, null], [null, 1], [20, 20]])
  })

  it('un salto de línea final no suma una línea de contexto', () => {
    expect(parseDiff('@@ -1 +1 @@\n-a\n+b\n')).toHaveLength(3)
  })

  it('vacío da lista vacía', () => {
    expect(parseDiff('')).toEqual([])
  })
})
