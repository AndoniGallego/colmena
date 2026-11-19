import { describe, expect, it } from 'vitest'
import { escenaDe } from './bloque'
import { toEstructura, type DiagramaEstructura } from './diagrama'
import { layoutDiagrama } from './diagramaLayout'
import { envolver, medirAprox, solapan, type Escena } from './escena'
import { toPasos } from './pasos'
import { escenaProceso, escenaSecuencia, grafoDeProceso, ordenRecorrido } from './pasosEscena'

function rng(seed: number) {
  let s = seed >>> 0
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0
    return s / 2 ** 32
  }
}

function azar(seed: number, n: number, m: number, grupos: number): DiagramaEstructura {
  const r = rng(seed)
  return toEstructura({
    grupos: Array.from({ length: grupos }, (_, i) => ({ id: `g${i}`, nombre: `Grupo ${i}` })),
    nodos: Array.from({ length: n }, (_, i) => ({
      id: `n${i}`,
      nombre: `Nodo ${i} ${'palabra '.repeat(Math.floor(r() * 5))}`,
      icono: r() < 0.5 ? '🧩' : '',
      tipo: ['app', 'servicio', 'datos', 'persona', 'decision', 'nota', 'externo', 'caja'][Math.floor(r() * 8)],
      grupo: grupos && r() < 0.6 ? `g${Math.floor(r() * grupos)}` : undefined,
    })),
    conexiones: Array.from({ length: m }, () => ({ de: `n${Math.floor(r() * n)}`, a: `n${Math.floor(r() * n)}`, texto: r() < 0.4 ? 'manda algo' : '' })),
  })!
}

function finito(e: Escena) {
  const nums = JSON.stringify(e).match(/-?\d+(\.\d+)?(e[-+]?\d+)?|NaN|Infinity/g) ?? []
  return !nums.some((x) => x === 'NaN' || x === 'Infinity')
}

function sinSolapes(e: Escena) {
  for (let i = 0; i < e.nodos.length; i++)
    for (let j = i + 1; j < e.nodos.length; j++) if (solapan(e.nodos[i], e.nodos[j])) return `${e.nodos[i].key}/${e.nodos[j].key}`
  // a group box never covers a node from outside the group, and group boxes never overlap
  for (const g of e.grupos) {
    const gi = Number(g.key.slice(1))
    for (const n of e.nodos) if (n.grupo !== gi && solapan(g, n)) return `${g.key} cubre ${n.key}`
    for (const o of e.grupos) if (o !== g && solapan(g, o)) return `${g.key}/${o.key}`
    for (const n of e.nodos) if (n.grupo === gi && !(n.x >= g.x && n.y >= g.y && n.x + n.w <= g.x + g.w && n.y + n.h <= g.y + g.h)) return `${n.key} fuera de ${g.key}`
  }
  return ''
}

const DENTRO = (e: Escena) => [...e.nodos, ...e.grupos, ...e.aristas.flatMap((a) => (a.etiqueta ? [a.etiqueta] : []))].every((b) => b.x >= 0 && b.y >= 0 && b.x + b.w <= e.w + 0.5 && b.y + b.h <= e.h + 0.5)

describe('layoutDiagrama', () => {
  it('lays a chain left to right or top to bottom', () => {
    const d = toEstructura({ nodos: [{ id: 'a' }, { id: 'b' }, { id: 'c' }], conexiones: [{ de: 'a', a: 'b' }, { de: 'b', a: 'c' }] })!
    const h = layoutDiagrama(d, { direccion: 'horizontal' })
    expect(h.nodos[0].x).toBeLessThan(h.nodos[1].x)
    expect(h.nodos[1].x).toBeLessThan(h.nodos[2].x)
    expect(new Set(h.nodos.map((n) => n.y + n.h / 2)).size).toBe(1)
    const v = layoutDiagrama(d, { direccion: 'vertical' })
    expect(v.nodos[0].y).toBeLessThan(v.nodos[1].y)
    expect(v.aristas).toHaveLength(2)
    expect(v.aristas[0].d).toMatch(/^M[\d.]+,[\d.]+C/)
    expect(v.aristas[0].punta).toMatch(/Z$/)
  })

  it('terminates on cycles and keeps every edge', () => {
    const d = toEstructura({
      nodos: ['a', 'b', 'c', 'd'].map((id) => ({ id })),
      conexiones: [{ de: 'a', a: 'b' }, { de: 'b', a: 'c' }, { de: 'c', a: 'a' }, { de: 'c', a: 'd' }, { de: 'd', a: 'b' }, { de: 'b', a: 'a' }],
    })!
    const e = layoutDiagrama(d, { direccion: 'vertical' })
    expect(e.aristas).toHaveLength(6)
    expect(sinSolapes(e)).toBe('')
    expect(finito(e)).toBe(true)
  })

  it('handles a lone node and nodes without edges', () => {
    const e = layoutDiagrama(toEstructura({ nodos: [{ id: 'solo' }] })!, { direccion: 'horizontal' })
    expect(e.nodos).toHaveLength(1)
    expect(e.w).toBeGreaterThan(e.nodos[0].w)
    const many = layoutDiagrama(toEstructura({ nodos: Array.from({ length: 6 }, (_, i) => ({ id: `n${i}` })) })!, { direccion: 'vertical' })
    expect(sinSolapes(many)).toBe('')
  })

  it('puts groups around their members without covering others', () => {
    const d = toEstructura({
      grupos: [{ id: 'app', nombre: 'Tu compu' }, { id: 'nube', nombre: 'La nube' }],
      nodos: [
        { id: 'yo', nombre: 'Vos', tipo: 'persona' },
        { id: 'web', nombre: 'La app', grupo: 'app' },
        { id: 'api', nombre: 'El servidor', grupo: 'app' },
        { id: 'db', nombre: 'Base de datos', grupo: 'nube', tipo: 'datos' },
        { id: 'cola', nombre: 'Cola', grupo: 'nube' },
        { id: 'mail', nombre: 'Correo', tipo: 'externo' },
      ],
      conexiones: [
        { de: 'yo', a: 'web', texto: 'abre la app' },
        { de: 'web', a: 'api', texto: 'pide datos' },
        { de: 'api', a: 'db' },
        { de: 'api', a: 'cola', texto: 'deja un aviso' },
        { de: 'cola', a: 'mail' },
        { de: 'yo', a: 'mail', texto: 'recibe' },
      ],
    })!
    for (const direccion of ['horizontal', 'vertical'] as const) {
      const e = layoutDiagrama(d, { direccion })
      expect(e.grupos).toHaveLength(2)
      expect(sinSolapes(e)).toBe('')
      expect(DENTRO(e)).toBe(true)
    }
  })

  it('keeps labels apart from each other within a gap', () => {
    const d = toEstructura({
      nodos: ['a', 'b', 'c', 'd'].map((id) => ({ id })),
      conexiones: [{ de: 'a', a: 'c', texto: 'uno largo de verdad' }, { de: 'a', a: 'd', texto: 'dos largo de verdad' }, { de: 'b', a: 'c', texto: 'tres' }, { de: 'b', a: 'd', texto: 'cuatro' }],
    })!
    for (const direccion of ['horizontal', 'vertical'] as const) {
      const ls = layoutDiagrama(d, { direccion }).aristas.map((a) => a.etiqueta!)
      for (let i = 0; i < ls.length; i++) for (let j = i + 1; j < ls.length; j++) expect(solapan(ls[i], ls[j])).toBe(false)
    }
  })

  it('never overlaps, stays finite and fast on random graphs at the limits', () => {
    const t0 = Date.now()
    for (let seed = 1; seed <= 40; seed++) {
      const d = azar(seed, 5 + (seed % 36), 4 + ((seed * 7) % 77), seed % 5)
      for (const direccion of ['horizontal', 'vertical'] as const) {
        const e = layoutDiagrama(d, { direccion, compacto: seed % 2 === 0 })
        expect(sinSolapes(e), `seed ${seed} ${direccion}`).toBe('')
        expect(finito(e)).toBe(true)
        expect(DENTRO(e)).toBe(true)
        expect(e.aristas).toHaveLength(d.conexiones.length)
      }
    }
    const big = azar(99, 40, 80, 6)
    const e = layoutDiagrama(big, { direccion: 'vertical' })
    expect(sinSolapes(e)).toBe('')
    expect(Date.now() - t0).toBeLessThan(8000)
  })
})

describe('envolver', () => {
  it('wraps, cuts long words and ellipsizes past the line cap', () => {
    expect(envolver('hola mundo', 1000, 13, 400, medirAprox)).toEqual(['hola mundo'])
    const ls = envolver('una frase bastante larga que no entra en una sola línea angosta', 80, 13, 400, medirAprox, 2)
    expect(ls).toHaveLength(2)
    expect(ls[1].endsWith('…')).toBe(true)
    for (const l of envolver('x'.repeat(200), 60, 13, 400, medirAprox, 3)) expect(medirAprox(l, 13, 400)).toBeLessThanOrEqual(60 + 13)
  })
})

describe('pasos as diagrams', () => {
  const bife = toPasos({
    tipo: 'proceso',
    pasos: [
      { id: 'p1', texto: 'Sellar la carne', duracion: '3 min' },
      { id: 'p2', texto: 'Revisar el punto', decision: { pregunta: '¿Está dorada?', si: 'p3', no: 'p1' } },
      { id: 'p3', texto: 'Dejar descansar' },
    ],
  })!

  it('turns a process into boxes, a diamond, yes/no arrows and start/end', () => {
    const { grafo, nodosDePaso } = grafoDeProceso(bife)
    expect(grafo.nodos.map((n) => n.forma)).toEqual(['terminal', 'caja', 'caja', 'decision', 'caja', 'terminal'])
    expect(grafo.aristas.filter((a) => a.trazo === 'si' || a.trazo === 'no').map((a) => a.texto)).toEqual(['Sí', 'No'])
    expect(nodosDePaso[1]).toHaveLength(2)
    const e = escenaProceso(bife, 'vertical')
    expect(sinSolapes(e)).toBe('')
    expect(e.pasos).toHaveLength(3)
    expect(e.nodos.find((n) => n.forma === 'decision')!.lineas.join(' ')).toBe('¿Está dorada?')
  })

  it('walks the main route first', () => {
    const f = toPasos({ tipo: 'proceso', pasos: [{ id: 'a', texto: 'A', decision: { pregunta: '?', si: 'c', no: 'b' } }, { id: 'b', texto: 'B' }, { id: 'c', texto: 'C' }] })!
    expect(ordenRecorrido(f)).toEqual([0, 2, 1])
  })

  it('draws a sequence with lifelines and one numbered arrow per step', () => {
    const f = toPasos({
      tipo: 'secuencia',
      actores: [{ id: 'a', nombre: 'Claude' }, { id: 'b', nombre: 'Orquestador' }, { id: 'c', nombre: 'Tu celu' }],
      pasos: [
        { de: 'a', texto: 'Termina' },
        { de: 'a', a: 'b', texto: 'Avisa que terminó' },
        { de: 'b', a: 'c', texto: 'Manda el aviso', tipo: 'respuesta' },
        { de: 'c', a: 'a', texto: 'Vuelve', tipo: 'error' },
      ],
    })!
    const e = escenaSecuencia(f)
    expect(e.lineas).toHaveLength(3)
    expect(e.aristas.map((a) => a.num)).toEqual(['1', '2', '3', '4'])
    expect(e.aristas.map((a) => a.trazo)).toEqual(['evento', 'llamada', 'respuesta', 'error'])
    expect(e.aristas[0].d).toBe('')
    const ys = e.aristas.map((a) => a.etiqueta!.y)
    expect([...ys].sort((x, y) => x - y)).toEqual(ys)
    expect(e.pasos[1]).toEqual(['e1', 'n0', 'n1'])
    expect(DENTRO(e)).toBe(true)
  })

  it('picks the orientation that fits the room', () => {
    const d = toEstructura({ nodos: ['a', 'b', 'c', 'd', 'e'].map((id) => ({ id, nombre: `Paso ${id}` })), conexiones: [{ de: 'a', a: 'b' }, { de: 'b', a: 'c' }, { de: 'c', a: 'd' }, { de: 'd', a: 'e' }] })!
    expect(escenaDe(d, 360, 2000).direccion).toBe('vertical')
    expect(escenaDe(d, 1400, 300).direccion).toBe('horizontal')
    expect(escenaDe({ ...d, direccion: 'horizontal' }, 360, 2000).direccion).toBe('horizontal')
  })
})
