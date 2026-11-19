import type { Direccion } from './diagrama'
import { layoutGrafo, type GArista, type GNodo, type Grafo } from './diagramaLayout'
import { anchoLineas, envolver, medirAprox, punta, r1, type EArista, type ENodo, type ELinea, type Escena, type Medir, type Trazo } from './escena'
import { numeroPaso, ruta, type DiagramaPasos } from './pasos'

/** Order of the guided walk: the main route first, then the steps off it. */
export function ordenRecorrido(f: DiagramaPasos): number[] {
  const r = ruta(f)
  return [...r, ...f.pasos.map((_, i) => i).filter((i) => !r.includes(i))]
}

/** A "proceso" as a flowchart: one box per step, a diamond after each decision, Inicio/Fin pills. */
export function grafoDeProceso(f: DiagramaPasos): { grafo: Grafo; nodosDePaso: number[][] } {
  const nodos: GNodo[] = []
  const aristas: GArista[] = []
  const base = { icono: '', sub: '', num: '', detalle: '', datos: '', tipoTexto: '', grupo: -1 }
  const inicio = nodos.push({ ...base, forma: 'terminal', tono: 'acento', nombre: 'Inicio' }) - 1
  const caja: number[] = []
  const rombo: number[] = []
  f.pasos.forEach((p, i) => {
    caja[i] = nodos.push({
      ...base,
      forma: 'caja',
      tono: 'neutro',
      nombre: p.texto,
      icono: p.icono,
      sub: p.duracion ? `⏱ ${p.duracion}` : '',
      num: String(numeroPaso(f, i)),
      detalle: p.detalle,
      datos: p.datos,
      tipoTexto: 'Paso',
    }) - 1
    rombo[i] = p.decision ? nodos.push({ ...base, forma: 'decision', tono: 'ambar', nombre: p.decision.pregunta, tipoTexto: 'Decisión', detalle: p.detalle }) - 1 : -1
  })
  let fin = -1
  const alFin = () => (fin >= 0 ? fin : (fin = nodos.push({ ...base, forma: 'terminal', tono: 'gris', nombre: 'Fin' }) - 1))
  aristas.push({ de: inicio, a: caja[0], texto: '', trazo: 'llamada' })
  f.pasos.forEach((p, i) => {
    if (p.decision) {
      aristas.push({ de: caja[i], a: rombo[i], texto: '', trazo: 'llamada' })
      const d = p.decision
      aristas.push({ de: rombo[i], a: d.si >= 0 ? caja[d.si] : alFin(), texto: 'Sí', trazo: 'si' })
      aristas.push({ de: rombo[i], a: d.no >= 0 ? caja[d.no] : alFin(), texto: 'No', trazo: 'no' })
    } else aristas.push({ de: caja[i], a: i + 1 < f.pasos.length ? caja[i + 1] : alFin(), texto: '', trazo: 'llamada' })
  })
  return {
    grafo: { nodos, aristas: aristas.filter((a) => a.de !== a.a), grupos: [] },
    nodosDePaso: f.pasos.map((_, i) => (rombo[i] >= 0 ? [caja[i], rombo[i]] : [caja[i]])),
  }
}

export function escenaProceso(f: DiagramaPasos, direccion: Direccion, medir: Medir = medirAprox, compacto = false): Escena {
  const { grafo, nodosDePaso } = grafoDeProceso(f)
  const esc = layoutGrafo(grafo, { direccion, medir, compacto, tipo: 'proceso' })
  const salida = (n: number) => esc.aristas.filter((a) => a.de === `n${n}`).map((a) => a.key)
  esc.pasos = ordenRecorrido(f).map((i) => {
    const ns = nodosDePaso[i]
    return [...ns.map((n) => `n${n}`), ...salida(ns[ns.length - 1])]
  })
  return esc
}

const TRAZO: Record<string, Trazo> = { llamada: 'llamada', respuesta: 'respuesta', error: 'error', evento: 'evento' }

/** A "secuencia" as a classic sequence diagram: actors on top, lifelines, one numbered arrow per step. */
export function escenaSecuencia(f: DiagramaPasos, medir: Medir = medirAprox, compacto = false): Escena {
  const M = 22
  const A = f.actores
  const cab = A.map((a) => {
    const lineas = envolver(a.nombre, compacto ? 78 : 118, 13, 600, medir, 2)
    const tw = anchoLineas(lineas, 13, 600, medir)
    return { lineas, w: Math.ceil(Math.max(compacto ? 64 : 92, tw + (a.icono && !compacto ? 34 : 0) + 26)), h: Math.max(48, lineas.length * 17 + 24) }
  })
  const cabH = Math.max(...cab.map((c) => c.h))
  const ETQ = 11.5
  // room each pair of neighbours needs: their halves plus the widest label that only spans them
  const sep = A.slice(1).map((_, k) => Math.max((cab[k].w + cab[k + 1].w) / 2 + (compacto ? 14 : 22), compacto ? 88 : 150))
  for (const p of f.pasos) {
    if (p.de === p.a) {
      const w = Math.min(medir(p.texto, ETQ, 500) + 30, compacto ? 130 : 210) / 2 + (compacto ? 18 : 26)
      if (p.de > 0) sep[p.de - 1] = Math.max(sep[p.de - 1], w)
      if (p.de < sep.length) sep[p.de] = Math.max(sep[p.de], w)
      continue
    }
    const lo = Math.min(p.de, p.a)
    const hi = Math.max(p.de, p.a)
    const quiere = Math.min(medir(p.texto, ETQ, 500) + 44, compacto ? 140 : 270)
    const tiene = sep.slice(lo, hi).reduce((s, x) => s + x, 0)
    if (tiene < quiere) for (let k = lo; k < hi; k++) sep[k] += (quiere - tiene) / (hi - lo)
  }
  const xs: number[] = []
  let x = M + cab[0].w / 2
  A.forEach((_, i) => {
    if (i) x += sep[i - 1]
    xs.push(x)
  })

  const nodos: ENodo[] = A.map((a, i) => ({
    key: `n${i}`,
    x: r1(xs[i] - cab[i].w / 2),
    y: M,
    w: cab[i].w,
    h: cabH,
    forma: 'actor',
    tono: 'acento',
    lineas: cab[i].lineas,
    // on narrow screens the icon would cost a column its width: the name is what matters
    icono: compacto ? '' : a.icono,
    sub: '',
    num: '',
    nombre: a.nombre,
    detalle: '',
    datos: '',
    tipoTexto: 'Participante',
    grupo: -1,
    rank: 0,
  }))

  const aristas: EArista[] = []
  let y = M + cabH + 26
  f.pasos.forEach((p, k) => {
    const num = String(k + 1)
    const trazo = TRAZO[p.de === p.a ? 'evento' : p.tipo] ?? 'llamada'
    const base = { key: `e${k}`, de: `n${p.de}`, a: `n${p.a}`, num, titulo: p.texto, detalle: p.detalle, datos: p.datos, propia: true, rank: k }
    if (p.de === p.a) {
      const lineas = envolver(p.texto, compacto ? 110 : 190, ETQ, 500, medir, 4)
      const w = Math.ceil(anchoLineas(lineas, ETQ, 500, medir) + 22)
      const h = lineas.length * 14 + 14
      const et = { lineas, w, h, x: r1(xs[p.de] - w / 2), y: r1(y) }
      aristas.push({ ...base, d: '', trazo: p.tipo === 'error' ? 'error' : 'evento', punta: '', etiqueta: et, numPos: { x: r1(et.x - 13), y: r1(y + h / 2) } })
      y += h + 22
      return
    }
    const x1 = xs[p.de]
    const x2 = xs[p.a]
    const dir = Math.sign(x2 - x1)
    const span = Math.abs(x2 - x1)
    const lineas = envolver(p.texto, Math.max(compacto ? 64 : 80, span - (compacto ? 30 : 44)), ETQ, 500, medir, 4)
    const w = Math.ceil(anchoLineas(lineas, ETQ, 500, medir) + 12)
    const h = lineas.length * 14 + 4
    const ay = y + h + 8
    const ini = x1 + dir * 13
    const fin = x2 - dir * 1.5
    aristas.push({
      ...base,
      d: `M${r1(ini)},${r1(ay)}L${r1(fin - dir * 7)},${r1(ay)}`,
      trazo,
      punta: punta(fin, ay, dir, 0),
      etiqueta: { lineas, w, h, x: r1((x1 + x2) / 2 - w / 2 + dir * 6), y: r1(y) },
      numPos: { x: r1(x1), y: r1(ay) },
    })
    y = ay + 26
  })
  const fondo = y + 6
  const lineas: ELinea[] = A.map((_, i) => ({ key: `n${i}`, x: r1(xs[i]), y1: M + cabH, y2: r1(fondo) }))
  let w = xs[xs.length - 1] + cab[cab.length - 1].w / 2
  for (const a of aristas) if (a.etiqueta) w = Math.max(w, a.etiqueta.x + a.etiqueta.w)
  const minX = Math.min(M, ...aristas.flatMap((a) => (a.numPos ? [a.numPos.x - 12] : [])), ...aristas.flatMap((a) => (a.etiqueta ? [a.etiqueta.x] : [])))
  const esc: Escena = {
    tipo: 'secuencia',
    direccion: 'vertical',
    w: Math.ceil(w + M),
    h: Math.ceil(fondo + M),
    nodos,
    aristas,
    grupos: [],
    lineas,
    pasos: f.pasos.map((p, k) => [`e${k}`, `n${p.de}`, `n${p.a}`]),
  }
  if (minX < M) desplazar(esc, M - minX)
  return esc
}

function desplazar(esc: Escena, dx: number) {
  const mover = (d: string) => d.replace(/(-?\d+(?:\.\d+)?),/g, (_, n: string) => `${r1(Number(n) + dx)},`)
  for (const n of esc.nodos) n.x = r1(n.x + dx)
  for (const l of esc.lineas) l.x = r1(l.x + dx)
  for (const a of esc.aristas) {
    a.d = mover(a.d)
    a.punta = mover(a.punta)
    if (a.etiqueta) a.etiqueta.x = r1(a.etiqueta.x + dx)
    if (a.numPos) a.numPos.x = r1(a.numPos.x + dx)
  }
  esc.w = Math.ceil(esc.w + dx)
}
