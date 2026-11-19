import { describe, expect, it } from 'vitest'
import { diagramaLegado, fenceCanonico, LEGACY_FENCE } from './legado'
import { plainPreview } from './preview'
import { parseSegments } from './segments'

const viejo = (j: unknown) => '```' + LEGACY_FENCE + '\n' + JSON.stringify(j) + '\n```'

describe('fence de mensajes viejos', () => {
  it('se lee como un diagrama de secuencia o de proceso', () => {
    const seq = { titulo: 'S', actores: [{ id: 'a', nombre: 'A' }, { id: 'b', nombre: 'B' }], pasos: [{ de: 'a', a: 'b', texto: 'Hola' }] }
    const proc = { titulo: 'P', pasos: [{ id: 'p1', texto: 'Uno' }] }
    const segs = parseSegments(`Antes\n\n${viejo(seq)}\n\n${viejo(proc)}`)
    expect(segs.map((s) => s.type)).toEqual(['md', 'diagrama', 'diagrama'])
    expect(segs.flatMap((s) => (s.type === 'diagrama' ? [s.data.tipo] : []))).toEqual(['secuencia', 'proceso'])
  })

  it('infiere el tipo como antes cuando falta', () => {
    expect(diagramaLegado({ actores: [{ id: 'a' }], pasos: [{ de: 'a', texto: 'x' }] })!.tipo).toBe('secuencia')
    expect(diagramaLegado({ pasos: [{ texto: 'x' }] })!.tipo).toBe('proceso')
    expect(diagramaLegado({ nodos: [{ id: 'a' }] })).toBeNull()
  })

  it('JSON inválido queda como código y mientras llega muestra "Armando el diagrama"', () => {
    expect(parseSegments(viejo('x').replace('"x"', '{"pasos": ['))[0].type).toBe('md')
    expect(parseSegments('Va\n```' + LEGACY_FENCE + '\n{"titu', true).at(-1)).toEqual({ type: 'pending', kind: 'diagrama' })
  })

  it('en los avisos se nombra como diagrama', () => {
    expect(plainPreview(viejo({ titulo: 'Cocinar', tipo: 'proceso', pasos: [] }))).toBe('Diagrama: Cocinar.')
  })

  it('normaliza el nombre del fence', () => {
    expect(fenceCanonico(LEGACY_FENCE.toUpperCase())).toBe('diagrama')
    expect(fenceCanonico('opciones')).toBe('opciones')
  })
})
