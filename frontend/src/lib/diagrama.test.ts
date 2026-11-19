import { describe, expect, it } from 'vitest'
import { iconoDe, LIM, MAX_CONEXIONES, MAX_NODOS, MAX_NOTAS, toDiagrama, toEstructura } from './diagrama'
import { parseSegments } from './segments'

const base = {
  titulo: 'Arquitectura',
  grupos: [{ id: 'nube', nombre: 'En la nube', color: 'azul' }, { id: 'vacio', nombre: 'Nadie' }],
  nodos: [
    { id: 'yo', nombre: 'Vos', icono: '🙂', tipo: 'persona' },
    { id: 'app', nombre: 'La app', grupo: 'nube', tipo: 'app' },
    { id: 'db', nombre: 'Base', grupo: 'nube', tipo: 'datos', detalle: 'Guarda todo' },
  ],
  conexiones: [
    { de: 'yo', a: 'app', texto: 'abre', tipo: 'llamada' },
    { de: 'app', a: 'db', tipo: 'datos' },
  ],
}

describe('toEstructura', () => {
  it('normalizes a valid diagram', () => {
    const d = toEstructura(base)!
    expect(d.titulo).toBe('Arquitectura')
    expect(d.nodos.map((n) => n.id)).toEqual(['yo', 'app', 'db'])
    expect(d.nodos[0]).toMatchObject({ tipo: 'persona', icono: '🙂', grupo: -1 })
    expect(d.grupos).toEqual([{ id: 'nube', nombre: 'En la nube', color: 'azul' }])
    expect(d.nodos[1].grupo).toBe(0)
    expect(d.conexiones).toEqual([
      { de: 0, a: 1, texto: 'abre', tipo: 'llamada' },
      { de: 1, a: 2, texto: '', tipo: 'datos' },
    ])
    expect(d.direccion).toBeNull()
  })

  it('rejects what has nothing to draw', () => {
    expect(toEstructura(null)).toBeNull()
    expect(toEstructura([])).toBeNull()
    expect(toEstructura({ nodos: 'x' })).toBeNull()
    expect(toEstructura({ nodos: [] })).toBeNull()
    expect(toEstructura({ nodos: [{ nombre: 'sin id' }, 3, null] })).toBeNull()
  })

  it('drops bad connections, duplicates and self loops; unknown types fall back', () => {
    const d = toEstructura({
      nodos: [{ id: 'a', tipo: 'nave' }, { id: 'b' }, { id: 'a', nombre: 'dup' }],
      conexiones: [{ de: 'a', a: 'zz' }, { de: 'a', a: 'a' }, { de: 'a', a: 'b', tipo: 'x' }, { de: 'a', a: 'b', tipo: 'x' }, 'nada'],
      direccion: 'diagonal',
    })!
    expect(d.nodos).toHaveLength(2)
    expect(d.nodos[0]).toMatchObject({ nombre: 'a', tipo: 'caja' })
    expect(d.conexiones).toEqual([{ de: 0, a: 1, texto: '', tipo: 'llamada' }])
    expect(d.direccion).toBeNull()
  })

  it('clips every text and caps the lists', () => {
    const largo = 'x'.repeat(1000)
    const d = toEstructura({
      titulo: largo,
      resumen: largo,
      direccion: 'vertical',
      nodos: Array.from({ length: 60 }, (_, i) => ({ id: `n${i}`, nombre: largo, detalle: largo })),
      conexiones: Array.from({ length: 200 }, (_, i) => ({ de: `n${i % 40}`, a: `n${(i + 1) % 40}`, texto: `${i} ${largo}` })),
      notas: Array.from({ length: 10 }, () => largo),
    })!
    expect(d.titulo.length).toBe(LIM.titulo)
    expect(d.resumen.length).toBe(LIM.resumen)
    expect(d.nodos).toHaveLength(MAX_NODOS)
    expect(d.nodos[0].nombre.length).toBe(LIM.nombre)
    expect(d.nodos[0].detalle.length).toBe(LIM.detalle)
    expect(d.conexiones.length).toBe(MAX_CONEXIONES)
    expect(d.conexiones[0].texto.length).toBe(LIM.texto)
    expect(d.notas).toHaveLength(MAX_NOTAS)
    expect(d.direccion).toBe('vertical')
  })

  it('never passes markup or control characters through as anything but text', () => {
    const d = toEstructura({ nodos: [{ id: 'a', nombre: '<img src=x onerror=alert(1)>‮\u0007 hola', icono: '<b>' }] })!
    expect(d.nodos[0].nombre).toBe('<img src=x onerror=alert(1)> hola')
    expect(d.nodos[0].icono).toBe('')
  })

  it('assigns palette colors and accepts aliases', () => {
    const d = toEstructura({
      grupos: [{ id: 'a', color: 'purple' }, { id: 'b', color: 'url(javascript:x)' }],
      nodos: [{ id: 'x', grupo: 'a' }, { id: 'y', grupo: 'b' }, { id: 'z', grupo: 'nope' }],
    })!
    expect(d.grupos.map((g) => g.color)).toEqual(['violeta', 'verde'])
    expect(d.nodos[2].grupo).toBe(-1)
  })
})

describe('iconoDe', () => {
  it('keeps one emoji and rejects words', () => {
    expect(iconoDe('🚀 extra')).toBe('🚀')
    expect(iconoDe('👩‍💻')).toBe('👩‍💻')
    expect(iconoDe('abc')).toBe('')
    expect(iconoDe(3)).toBe('')
  })
})

describe('toDiagrama', () => {
  it('defaults to estructura and accepts it explicitly', () => {
    expect(toDiagrama(base)!.tipo).toBe('estructura')
    expect(toDiagrama({ ...base, tipo: 'estructura' })!.tipo).toBe('estructura')
  })

  it('reads secuencia and proceso from "tipo"', () => {
    const seq = toDiagrama({ tipo: 'secuencia', actores: [{ id: 'a', nombre: 'A' }], pasos: [{ de: 'a', texto: 'Hola' }] })!
    expect(seq.tipo).toBe('secuencia')
    const proc = toDiagrama({ tipo: 'proceso', pasos: [{ id: 'p1', texto: 'Uno' }] })!
    expect(proc.tipo).toBe('proceso')
  })

  it('rejects unknown tipos and shapes that do not match the tipo', () => {
    expect(toDiagrama({ ...base, tipo: 'raro' })).toBeNull()
    expect(toDiagrama({ tipo: 'secuencia', pasos: [{ texto: 'x' }] })).toBeNull()
    expect(toDiagrama({ tipo: 'proceso', nodos: base.nodos })).toBeNull()
    expect(toDiagrama({ pasos: [{ texto: 'sin tipo no es estructura' }] })).toBeNull()
  })
})

describe('segments with diagrams', () => {
  it('turns each ```diagrama block into its own segment, whatever its tipo', () => {
    const proceso = '```diagrama\n' + JSON.stringify({ tipo: 'proceso', pasos: [{ texto: 'Uno' }] }) + '\n```'
    const segs = parseSegments(`Mirá\n\n\`\`\`diagrama\n${JSON.stringify(base)}\n\`\`\`\n\nY\n\n${proceso}`)
    expect(segs.map((s) => s.type)).toEqual(['md', 'diagrama', 'md', 'diagrama'])
    expect(segs.flatMap((s) => (s.type === 'diagrama' ? [s.data.tipo] : []))).toEqual(['estructura', 'proceso'])
  })

  it('leaves an invalid diagram as code', () => {
    const segs = parseSegments('```diagrama\n{"nodos": [\n```')
    expect(segs.map((s) => s.type)).toEqual(['md'])
  })

  it('shows pending while the block streams', () => {
    expect(parseSegments('Va\n```diagrama\n{"nod', true).at(-1)).toEqual({ type: 'pending', kind: 'diagrama' })
  })
})
