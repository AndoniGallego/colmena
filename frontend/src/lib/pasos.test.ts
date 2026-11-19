import { describe, expect, it } from 'vitest'
import { actoresEnOrden, esVuelta, formatoMinutos, MAX_ACTORES, MAX_NOTAS, MAX_PASOS, minutosDe, nextOf, numeroPaso, ramas, resumenPasos, ruta, toPasos } from './pasos'
import { DIAGRAMA_BIFE } from '../mock/diagramasReales'
import { parseSegments } from './segments'

const seq = {
  titulo: 'Stock',
  resumen: 'Tienda pide stock',
  tipo: 'secuencia',
  actores: [{ id: 'tienda', nombre: 'Tienda', icono: '🛒' }, { id: 'mod', nombre: 'Módulo' }],
  pasos: [
    { de: 'tienda', a: 'mod', texto: 'Pide stock', detalle: 'GET /stock', datos: '{sku}', tipo: 'llamada' },
    { de: 'mod', a: 'tienda', texto: 'Devuelve', tipo: 'respuesta' },
    { de: 'mod', texto: 'Cachea' },
  ],
  notas: ['Una nota'],
}

describe('toPasos secuencia', () => {
  it('parses a valid sequence and resolves actors to indexes', () => {
    const f = toPasos(seq)!
    expect(f.tipo).toBe('secuencia')
    expect(f.actores).toEqual([{ id: 'tienda', nombre: 'Tienda', icono: '🛒' }, { id: 'mod', nombre: 'Módulo', icono: '' }])
    expect(f.pasos.map((p) => [p.de, p.a, p.tipo])).toEqual([[0, 1, 'llamada'], [1, 0, 'respuesta'], [1, 1, 'evento']])
    expect(f.notas).toEqual(['Una nota'])
  })

  it('drops steps that point at unknown actors and rejects when none is left', () => {
    const f = toPasos({ ...seq, pasos: [{ de: 'tienda', a: 'nadie', texto: 'x' }, { de: 'tienda', a: 'mod', texto: 'ok' }] })!
    expect(f.pasos).toHaveLength(1)
    expect(toPasos({ ...seq, pasos: [{ de: 'zzz', texto: 'x' }] })).toBeNull()
  })

  it('needs actors for a sequence', () => {
    expect(toPasos({ tipo: 'secuencia', pasos: [{ texto: 'x' }] })).toBeNull()
  })

  it('infers the type from the actors', () => {
    expect(toPasos({ ...seq, tipo: undefined })!.tipo).toBe('secuencia')
    expect(toPasos({ pasos: [{ texto: 'x' }] })!.tipo).toBe('proceso')
  })

  it('treats unknown step types as llamada', () => {
    expect(toPasos({ ...seq, pasos: [{ de: 'tienda', a: 'mod', texto: 'x', tipo: 'raro' }] })!.pasos[0].tipo).toBe('llamada')
  })
})

describe('toPasos proceso', () => {
  const proc = {
    tipo: 'proceso',
    pasos: [
      { id: 'a', texto: 'Sellar', duracion: '3 min', icono: '🔥' },
      { id: 'b', texto: 'Dorado?', decision: { pregunta: '¿Está dorada?', si: 'd', no: 'a' } },
      { id: 'c', texto: 'Intermedio' },
      { id: 'd', texto: 'Servir' },
    ],
  }

  it('links decisions to step indexes', () => {
    const f = toPasos(proc)!
    expect(f.pasos[1].decision).toEqual({ pregunta: '¿Está dorada?', si: 3, no: 0 })
    expect(f.pasos[0].duracion).toBe('3 min')
  })

  it('ignores branches that point nowhere and keeps ids unique', () => {
    const f = toPasos({ tipo: 'proceso', pasos: [{ id: 'x', texto: 'a', decision: { pregunta: '¿?', si: 'nope' } }, { id: 'x', texto: 'b' }] })!
    expect(f.pasos[0].decision).toEqual({ pregunta: '¿?', si: -1, no: -1 })
    expect(new Set(f.pasos.map((p) => p.id)).size).toBe(2)
  })

  it('walks the main path along "sí" and skips the alternative', () => {
    const f = toPasos(proc)!
    expect(ruta(f)).toEqual([0, 1, 3])
    expect(nextOf(f, 1)).toBe(3)
    expect(nextOf(f, 2)).toBe(3)
    expect(nextOf(f, 3)).toBeNull()
  })

  it('stops a loop on the main path', () => {
    const f = toPasos({ tipo: 'proceso', pasos: [{ id: 'a', texto: 'a' }, { id: 'b', texto: 'b', decision: { pregunta: '?', si: 'a', no: 'a' } }] })!
    expect(ruta(f)).toEqual([0, 1])
  })
})

describe('limits and invalid input', () => {
  it('caps actors, steps, notes and text length', () => {
    const actores = Array.from({ length: 20 }, (_, i) => ({ id: `a${i}`, nombre: 'n'.repeat(60) }))
    const pasos = Array.from({ length: 90 }, () => ({ de: 'a0', a: 'a1', texto: 't'.repeat(300), detalle: 'd'.repeat(900), datos: 'x'.repeat(400) }))
    const f = toPasos({ titulo: 'x'.repeat(300), actores, pasos, notas: Array.from({ length: 12 }, () => 'n') })!
    expect(f.actores).toHaveLength(MAX_ACTORES)
    expect(f.pasos).toHaveLength(MAX_PASOS)
    expect(f.notas).toHaveLength(MAX_NOTAS)
    expect(f.titulo).toHaveLength(100)
    expect(f.actores[0].nombre).toHaveLength(24)
    expect(f.pasos[0].texto).toHaveLength(120)
    expect(f.pasos[0].detalle).toHaveLength(400)
    expect(f.pasos[0].datos).toHaveLength(160)
  })

  it('rejects non objects and empty steps', () => {
    for (const v of [null, 'x', 3, [], {}, { pasos: [] }, { pasos: [{ detalle: 'sin texto' }] }]) expect(toPasos(v)).toBeNull()
  })

  it('keeps markup as plain text', () => {
    expect(toPasos({ tipo: 'proceso', pasos: [{ texto: '<img src=x onerror=alert(1)>' }] })!.pasos[0].texto).toBe('<img src=x onerror=alert(1)>')
  })
})

describe('secuencia and proceso blocks in a message', () => {
  const block = (j: string) => '```diagrama\n' + j + '\n```'
  it('turns a valid block into a segment', () => {
    const segs = parseSegments('Mirá:\n\n' + block(JSON.stringify(seq)))
    expect(segs.map((s) => s.type)).toEqual(['md', 'diagrama'])
  })
  it('shows invalid JSON as code', () => {
    const segs = parseSegments(block('{"pasos": ['))
    expect(segs).toHaveLength(1)
    expect(segs[0].type).toBe('md')
  })
  it('shows the placeholder while streaming', () => {
    expect(parseSegments('Dale\n```diagrama\n{"titulo": "x", "pas', true).map((s) => s.type)).toEqual(['md', 'pending'])
  })
})

describe('ramas y recorrido', () => {
  const bife = {
    tipo: 'proceso',
    pasos: [
      { id: 'p1', texto: 'Sacar' },
      { id: 'p3', texto: 'Sellar' },
      { id: 'p4', texto: 'Revisar', decision: { pregunta: '¿Punto?', si: 'p5', no: 'p3' } },
      { id: 'p5', texto: 'Descansar' },
    ],
  }
  const f = toPasos(bife)!

  it('flags a branch that targets the same or an earlier step', () => {
    expect(esVuelta(2, 1)).toBe(true)
    expect(esVuelta(2, 2)).toBe(true)
    expect(esVuelta(2, 3)).toBe(false)
    expect(esVuelta(2, -1)).toBe(false)
  })

  it('tells where each answer leads, saying when it goes back', () => {
    const r = ramas(f, 2)!
    expect(r.pregunta).toBe('¿Punto?')
    expect(r.si).toMatchObject({ a: 3, vuelve: false, numero: 4, aviso: 'Seguís en el paso 4: Descansar' })
    expect(r.no).toMatchObject({ a: 1, vuelve: true, numero: 2, aviso: 'Volvés al paso 2: Sellar' })
  })

  it('has no branches without a decision, and drops targets that do not exist', () => {
    expect(ramas(f, 0)).toBeNull()
    const g = toPasos({ ...bife, pasos: [bife.pasos[0], { ...bife.pasos[2], decision: { pregunta: '¿?', si: 'p1', no: 'zzz' } }] })!
    expect(ramas(g, 1)!.no).toBeNull()
    expect(ramas(g, 1)!.si!.vuelve).toBe(true)
  })

  it('numbers steps along the main route', () => {
    expect(numeroPaso(f, 3)).toBe(4)
  })
})

describe('resumen del recorrido', () => {
  it('parses durations and formats minutes', () => {
    expect(minutosDe('20 min')).toBe(20)
    expect(minutosDe('1,5 h')).toBe(90)
    expect(minutosDe('30 s')).toBe(0.5)
    expect(minutosDe('rápido')).toBeNull()
    expect(formatoMinutos(33)).toBe('~33 min')
    expect(formatoMinutos(65)).toBe('~1 h 5 min')
  })

  it('sums the durations along the route and counts the decisions', () => {
    const r = resumenPasos(toPasos(DIAGRAMA_BIFE)!)
    expect(r.pasos).toBe(6)
    expect(r.decisiones).toBe(1)
    expect(r.minutos).toBe(33)
    expect(r.linea).toBe('6 pasos · 1 decisión · ~33 min')
  })

  it('lists the actors of a sequence in order of appearance', () => {
    const f = toPasos(seq)!
    expect(actoresEnOrden(f).map((a) => f.actores[a].id)).toEqual(['tienda', 'mod'])
    expect(resumenPasos(f).linea).toBe('3 pasos')
  })
})
