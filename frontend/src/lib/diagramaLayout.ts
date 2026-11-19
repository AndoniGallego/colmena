import type { ColorGrupo, DiagramaEstructura, Direccion, NodoTipo } from './diagrama'
import {
  anchoLineas,
  envolver,
  medirAprox,
  punta,
  r1,
  type EArista,
  type EGrupo,
  type ENodo,
  type Escena,
  type Etiqueta,
  type Forma,
  type Medir,
  type Tono,
  type Trazo,
} from './escena'

/** Layered ("Sugiyama-lite") layout: break cycles, rank by longest path, route long edges through
 * dummy points, place units (groups or single nodes) along the cross axis without overlaps, then
 * draw rank-aligned cubic curves with spread ports and labels inside the gaps between ranks. */

export interface GNodo {
  forma: Forma
  tono: Tono
  nombre: string
  icono: string
  sub: string
  num: string
  detalle: string
  datos: string
  tipoTexto: string
  grupo: number
}

export interface GArista {
  de: number
  a: number
  texto: string
  trazo: Trazo
}

export interface Grafo {
  nodos: GNodo[]
  aristas: GArista[]
  grupos: { nombre: string; color: ColorGrupo }[]
}

export interface OpLayout {
  direccion: Direccion
  medir?: Medir
  compacto?: boolean
  tipo?: Escena['tipo']
}

const M = 22
const GP = 16
const GH = 26
const NODE_GAP = 18
const UNIT_GAP = 26
const DUMMY_GAP = 10
const DUMMY = 8
const LH = 17
const ETQ_PX = 11.5
const ETQ_LH = 14
const PASADAS = 8

export const TONO: Record<NodoTipo, Tono> = {
  caja: 'neutro', persona: 'verde', app: 'acento', servicio: 'cian', datos: 'violeta', externo: 'gris', nota: 'amarillo', decision: 'ambar',
}
export const TIPO_TEXTO: Record<NodoTipo, string> = {
  caja: '', persona: 'Persona', app: 'App', servicio: 'Servicio', datos: 'Datos', externo: 'Externo', nota: 'Nota', decision: 'Decisión',
}

export function grafoDeDiagrama(d: DiagramaEstructura): Grafo {
  return {
    grupos: d.grupos.map((g) => ({ nombre: g.nombre, color: g.color })),
    nodos: d.nodos.map((n) => ({
      forma: n.tipo,
      tono: TONO[n.tipo],
      nombre: n.nombre,
      icono: n.icono,
      sub: '',
      num: '',
      detalle: n.detalle,
      datos: '',
      tipoTexto: TIPO_TEXTO[n.tipo],
      grupo: n.grupo,
    })),
    aristas: d.conexiones.map((c) => ({ de: c.de, a: c.a, texto: c.texto, trazo: c.tipo })),
  }
}

interface Tam {
  w: number
  h: number
  lineas: string[]
}

function tamano(n: GNodo, medir: Medir, compacto: boolean): Tam {
  if (n.forma === 'terminal') {
    const lineas = envolver(n.nombre, 120, 12, 600, medir, 1)
    return { lineas, w: Math.ceil(Math.max(64, anchoLineas(lineas, 12, 600, medir) + 34)), h: 32 }
  }
  if (n.forma === 'decision') {
    const lineas = envolver(n.nombre, compacto ? 112 : 132, 13, 600, medir, 3)
    const tw = Math.max(48, anchoLineas(lineas, 13, 600, medir))
    const th = lineas.length * LH
    return { lineas, w: Math.ceil(Math.max(112, tw * 1.62 + 26)), h: Math.ceil(Math.max(70, th * 2.3 + 22)) }
  }
  const lineas = envolver(n.nombre, compacto ? 122 : 150, 13, 600, medir, 3)
  const tw = Math.max(anchoLineas(lineas, 13, 600, medir), n.sub ? medir(n.sub, 11, 500) : 0)
  const padX = n.forma === 'persona' ? 18 : 14
  const icon = n.icono ? 34 : 0
  const num = n.num ? 8 : 0
  let h = Math.max(46, lineas.length * LH + (n.sub ? 15 : 0) + 24)
  if (n.forma === 'datos') h += 10
  return { lineas, w: Math.ceil(Math.max(84, tw + icon + padX * 2 + num)), h: Math.ceil(h) }
}

interface Unidad {
  verts: number[]
  r0: number
  r1: number
  grupo: number
  top: number
  size: number
  colocada: boolean
  soloDummy: boolean
}

/** Closest top to `deseado` outside every blocked open interval. */
function libre(deseado: number, bloqueos: [number, number][]): number {
  if (!bloqueos.length) return deseado
  bloqueos.sort((a, b) => a[0] - b[0])
  const merged: [number, number][] = []
  for (const b of bloqueos) {
    const last = merged[merged.length - 1]
    if (last && b[0] <= last[1]) last[1] = Math.max(last[1], b[1])
    else merged.push([b[0], b[1]])
  }
  for (const [a, b] of merged) if (deseado > a && deseado < b) return deseado - a <= b - deseado ? a : b
  return deseado
}

export function layoutGrafo(g: Grafo, op: OpLayout): Escena {
  const medir = op.medir ?? medirAprox
  const H = op.direccion === 'horizontal'
  const compacto = !!op.compacto
  const N = g.nodos.length
  const E = g.aristas.length
  const tam = g.nodos.map((n) => tamano(n, medir, compacto))
  const hayGrupos = g.nodos.some((n) => n.grupo >= 0)

  // 1. break cycles with a DFS: edges back into the stack are reversed
  const salen: number[][] = Array.from({ length: N }, () => [])
  const entran = new Array(N).fill(0)
  g.aristas.forEach((e, i) => {
    salen[e.de].push(i)
    entran[e.a]++
  })
  const rev = new Array<boolean>(E).fill(false)
  const estado = new Uint8Array(N)
  const raices = [...Array(N).keys()].sort((a, b) => (entran[a] === 0 ? 0 : 1) - (entran[b] === 0 ? 0 : 1) || a - b)
  for (const r of raices) {
    if (estado[r]) continue
    const pila: [number, number][] = [[r, 0]]
    estado[r] = 1
    while (pila.length) {
      const top = pila[pila.length - 1]
      const [u, k] = top
      if (k >= salen[u].length) {
        estado[u] = 2
        pila.pop()
        continue
      }
      top[1]++
      const e = salen[u][k]
      const v = g.aristas[e].a
      if (estado[v] === 1) rev[e] = true
      else if (estado[v] === 0) {
        estado[v] = 1
        pila.push([v, 0])
      }
    }
  }
  const src = (e: number) => (rev[e] ? g.aristas[e].a : g.aristas[e].de)
  const dst = (e: number) => (rev[e] ? g.aristas[e].de : g.aristas[e].a)

  // 2. ranks: longest path, then sources move next to their first successor
  const succ: number[][] = Array.from({ length: N }, () => [])
  const pred: number[][] = Array.from({ length: N }, () => [])
  for (let e = 0; e < E; e++) {
    succ[src(e)].push(dst(e))
    pred[dst(e)].push(src(e))
  }
  const grado = pred.map((p) => p.length)
  const cola = [...Array(N).keys()].filter((i) => grado[i] === 0)
  const topo: number[] = []
  while (cola.length) {
    const u = cola.shift()!
    topo.push(u)
    for (const v of succ[u]) if (--grado[v] === 0) cola.push(v)
  }
  const rank = new Array(N).fill(0)
  for (const u of topo) for (const v of succ[u]) rank[v] = Math.max(rank[v], rank[u] + 1)
  for (let k = topo.length - 1; k >= 0; k--) {
    const u = topo[k]
    if (!pred[u].length && succ[u].length) rank[u] = Math.max(rank[u], Math.min(...succ[u].map((v) => rank[v])) - 1)
  }
  const R = N ? Math.max(...rank) + 1 : 1

  // 3. vertices: real nodes, then one dummy per rank crossed by a long edge
  const vRank = [...rank]
  const vCross = tam.map((t) => (H ? t.h : t.w))
  const vGrupo = g.nodos.map((n) => n.grupo)
  const caminos: number[][] = []
  for (let e = 0; e < E; e++) {
    const s = src(e)
    const t = dst(e)
    const cad = [s]
    const gr = vGrupo[s] >= 0 && vGrupo[s] === vGrupo[t] ? vGrupo[s] : -1
    for (let r = rank[s] + 1; r < rank[t]; r++) {
      cad.push(vRank.length)
      vRank.push(r)
      vCross.push(DUMMY)
      vGrupo.push(gr)
    }
    cad.push(t)
    caminos.push(cad)
  }
  const V = vRank.length
  const real = (v: number) => v < N
  const vecinos: number[][] = Array.from({ length: V }, () => [])
  for (const cad of caminos)
    for (let k = 1; k < cad.length; k++) {
      vecinos[cad[k - 1]].push(cad[k])
      vecinos[cad[k]].push(cad[k - 1])
    }

  // labels, wrapped once; each one lives in the middle gap its edge crosses
  const etq: (Etiqueta & { gap: number })[] = []
  const etqDe: number[] = new Array(E).fill(-1)
  for (let e = 0; e < E; e++) {
    const t = g.aristas[e].texto
    if (!t) continue
    const lineas = envolver(t, compacto ? 104 : 124, ETQ_PX, 500, medir, 3)
    const a = rank[src(e)]
    const b = rank[dst(e)]
    etqDe[e] = etq.length
    etq.push({ lineas, w: Math.ceil(anchoLineas(lineas, ETQ_PX, 500, medir) + 16), h: lineas.length * ETQ_LH + 8, x: 0, y: 0, gap: a + Math.floor((b - a - 1) / 2) })
  }

  // labels of edges inside one group must fit inside its box: per group and gap, the room they need side by side
  const etqGrupo = new Map<number, Map<number, number>>()
  for (let e = 0; e < E; e++) {
    const gr = g.nodos[src(e)].grupo
    if (etqDe[e] < 0 || gr < 0 || gr !== g.nodos[dst(e)].grupo) continue
    const l = etq[etqDe[e]]
    const m = etqGrupo.get(gr) ?? new Map<number, number>()
    m.set(l.gap, (m.has(l.gap) ? m.get(l.gap)! + 4 : 0) + (H ? l.h : l.w))
    etqGrupo.set(gr, m)
  }

  // 4. rank geometry
  const rankSize = new Array(R).fill(0)
  for (let v = 0; v < N; v++) rankSize[vRank[v]] = Math.max(rankSize[vRank[v]], H ? tam[v].w : tam[v].h)
  const gapSize = new Array(Math.max(0, R - 1)).fill(H ? 66 : 54)
  for (const l of etq) gapSize[l.gap] = Math.max(gapSize[l.gap], H ? l.w + 40 : l.h + 30)
  if (hayGrupos) for (let k = 0; k < gapSize.length; k++) gapSize[k] += 2 * GP + (H ? 0 : GH)
  const rankPos: number[] = []
  let cur = M + (hayGrupos ? GP + (H ? 0 : GH) : 0)
  for (let r = 0; r < R; r++) {
    rankPos.push(cur)
    cur += rankSize[r] + (gapSize[r] ?? 0)
  }

  // 5. units along the cross axis
  const unidades: Unidad[] = []
  const unidadDe = new Array<number>(V).fill(-1)
  const porGrupo = new Map<number, number>()
  for (let v = 0; v < V; v++) {
    const gr = vGrupo[v]
    let u = gr >= 0 ? porGrupo.get(gr) : undefined
    if (u === undefined) {
      u = unidades.length
      unidades.push({ verts: [], r0: vRank[v], r1: vRank[v], grupo: gr, top: 0, size: 0, colocada: false, soloDummy: true })
      if (gr >= 0) porGrupo.set(gr, u)
    }
    const un = unidades[u]
    un.verts.push(v)
    un.r0 = Math.min(un.r0, vRank[v])
    un.r1 = Math.max(un.r1, vRank[v])
    if (real(v)) un.soloDummy = false
    unidadDe[v] = u
  }
  const off = new Array<number>(V).fill(0)
  const centro = (v: number) => unidades[unidadDe[v]].top + off[v]

  function armar(un: Unidad, ordenar: boolean) {
    const filas = new Map<number, number[]>()
    for (const v of un.verts) filas.set(vRank[v], [...(filas.get(vRank[v]) ?? []), v])
    if (ordenar) {
      for (const [r, fila] of filas) {
        const bary = (v: number) => {
          const ns = vecinos[v].filter((w) => unidadDe[w] !== unidadDe[v] || vRank[w] !== r).filter((w) => unidades[unidadDe[w]].colocada)
          return ns.length ? ns.reduce((s, w) => s + centro(w), 0) / ns.length : centro(v)
        }
        const b = new Map(fila.map((v) => [v, bary(v)]))
        fila.sort((x, y) => b.get(x)! - b.get(y)! || x - y)
      }
    }
    const pila = (fila: number[]) => fila.reduce((s, v) => s + vCross[v], 0) + fila.slice(1).reduce((s, v, k) => s + (real(v) && real(fila[k]) ? NODE_GAP : DUMMY_GAP), 0)
    const dentro = Math.max(0, ...[...filas.values()].map(pila), ...(un.grupo >= 0 ? [...(etqGrupo.get(un.grupo)?.values() ?? [])].map((x) => x + 12) : []))
    const cab = un.grupo >= 0 ? GP + (H ? GH : 0) : 0
    un.size = dentro + (un.grupo >= 0 ? 2 * GP + (H ? GH : 0) : 0)
    for (const fila of filas.values()) {
      let y = cab + (dentro - pila(fila)) / 2
      fila.forEach((v, k) => {
        if (k) y += real(v) && real(fila[k - 1]) ? NODE_GAP : DUMMY_GAP
        off[v] = y + vCross[v] / 2
        y += vCross[v]
      })
    }
  }

  const choca = (a: Unidad, b: Unidad) => a !== b && a.r0 <= b.r1 && b.r0 <= a.r1
  const hueco = (a: Unidad, b: Unidad) => (a.soloDummy && b.soloDummy ? DUMMY_GAP : a.soloDummy || b.soloDummy ? UNIT_GAP * 0.6 : UNIT_GAP)

  function colocar(un: Unidad, inicial: boolean) {
    un.colocada = false
    let suma = 0
    let peso = 0
    for (const v of un.verts)
      for (const w of vecinos[v]) {
        const otra = unidades[unidadDe[w]]
        if (otra === un || !otra.colocada) continue
        suma += centro(w) - off[v]
        peso++
      }
    const otras = unidades.filter((o) => o.colocada && choca(o, un))
    let deseado: number
    if (peso) deseado = suma / peso
    else if (inicial) deseado = otras.length ? Math.max(...otras.map((o) => o.top + o.size + hueco(o, un))) : 0
    else deseado = un.top
    un.top = libre(deseado, otras.map((o) => [o.top - hueco(o, un) - un.size, o.top + o.size + hueco(o, un)]))
    un.colocada = true
  }

  const orden = [...unidades].sort((a, b) => a.r0 - b.r0 || a.verts[0] - b.verts[0])
  for (const un of orden) {
    armar(un, false)
    colocar(un, true)
  }
  for (let p = 0; p < PASADAS; p++) {
    const seq = p % 2 === 0 ? [...unidades].sort((a, b) => a.r0 - b.r0 || a.verts[0] - b.verts[0]) : [...unidades].sort((a, b) => b.r1 - a.r1 || a.verts[0] - b.verts[0])
    for (const un of seq) {
      armar(un, true)
      colocar(un, false)
    }
  }
  const minTop = Math.min(...unidades.map((u) => u.top))
  for (const un of unidades) un.top -= minTop

  // 6. coordinates
  const pos = (rk: number, cr: number) => (H ? { x: rk, y: cr } : { x: cr, y: rk })
  const nodos: ENodo[] = g.nodos.map((n, i) => {
    const r = vRank[i]
    const rk = rankPos[r] + (rankSize[r] - (H ? tam[i].w : tam[i].h)) / 2
    const cr = M + centro(i) - vCross[i] / 2
    const p = pos(rk, cr)
    return {
      key: `n${i}`,
      x: r1(p.x),
      y: r1(p.y),
      w: tam[i].w,
      h: tam[i].h,
      forma: n.forma,
      tono: n.tono,
      lineas: tam[i].lineas,
      icono: n.icono,
      sub: n.sub,
      num: n.num,
      nombre: n.nombre,
      detalle: n.detalle,
      datos: n.datos,
      tipoTexto: n.tipoTexto,
      grupo: n.grupo,
      rank: r,
    }
  })

  const grupos: EGrupo[] = []
  for (const un of unidades) {
    if (un.grupo < 0) continue
    const r0 = Math.min(...un.verts.filter(real).map((v) => vRank[v]))
    const r1_ = Math.max(...un.verts.filter(real).map((v) => vRank[v]))
    const a = rankPos[r0] - GP - (H ? 0 : GH)
    const b = rankPos[r1_] + rankSize[r1_] + GP
    const p = pos(a, M + un.top)
    const gr = g.grupos[un.grupo]
    grupos.push({ key: `g${un.grupo}`, x: r1(p.x), y: r1(p.y), w: r1(H ? b - a : un.size), h: r1(H ? un.size : b - a), nombre: gr?.nombre ?? '', color: gr?.color ?? 'gris' })
  }

  // 7. edges
  type P = { r: number; c: number }
  const puertoOff = new Map<string, number>()
  for (let v = 0; v < N; v++) {
    for (const lado of ['out', 'in'] as const) {
      const es = [...Array(E).keys()].filter((e) => (lado === 'out' ? caminos[e][0] === v : caminos[e][caminos[e].length - 1] === v))
      if (!es.length) continue
      const otro = (e: number) => {
        const c = caminos[e]
        return centro(lado === 'out' ? c[1] : c[c.length - 2])
      }
      es.sort((a, b) => otro(a) - otro(b) || a - b)
      const forma = g.nodos[v].forma
      const maxPaso = forma === 'decision' || forma === 'terminal' ? 7 : 13
      const paso = es.length > 1 ? Math.min(maxPaso, (vCross[v] * (forma === 'decision' ? 0.34 : 0.62)) / (es.length - 1)) : 0
      es.forEach((e, k) => puertoOff.set(`${e}${lado}`, (k - (es.length - 1) / 2) * paso))
    }
  }
  /** How far the outline sits inside the node box at a cross offset (round ends, diamonds, cylinder caps). */
  function hundido(v: number, o: number): number {
    const f = g.nodos[v].forma
    const half = vCross[v] / 2
    const largo = H ? tam[v].w : tam[v].h
    if (f === 'decision') return (largo / 2) * Math.min(1, Math.abs(o) / half)
    if ((f === 'persona' || f === 'terminal') && H) {
      const rr = tam[v].h / 2
      return rr - Math.sqrt(Math.max(0, rr * rr - o * o))
    }
    if (f === 'datos' && !H) return 5 * (1 - Math.sqrt(Math.max(0, 1 - (o / half) ** 2)))
    return 0
  }
  const aristas: EArista[] = g.aristas.map((ar, e) => {
    const cad = caminos[e]
    const s = cad[0]
    const t = cad[cad.length - 1]
    const oS = puertoOff.get(`${e}out`) ?? 0
    const oT = puertoOff.get(`${e}in`) ?? 0
    const rS = rankPos[vRank[s]] + (rankSize[vRank[s]] + (H ? tam[s].w : tam[s].h)) / 2 - hundido(s, oS)
    const rT = rankPos[vRank[t]] + (rankSize[vRank[t]] - (H ? tam[t].w : tam[t].h)) / 2 + hundido(t, oT)
    const pts: P[] = [{ r: rS, c: M + centro(s) + oS }]
    for (const d of cad.slice(1, -1)) {
      const r = vRank[d]
      pts.push({ r: rankPos[r], c: M + centro(d) }, { r: rankPos[r] + rankSize[r], c: M + centro(d) })
    }
    pts.push({ r: rT, c: M + centro(t) + oT })
    const FL = 7
    if (rev[e]) pts[0] = { ...pts[0], r: pts[0].r + FL }
    else pts[pts.length - 1] = { ...pts[pts.length - 1], r: pts[pts.length - 1].r - FL }
    // segments in DAG order: even = cubic across a gap, odd = straight through a dummy's band
    const segs: P[][] = []
    for (let k = 0; k + 1 < pts.length; k++) {
      const a = pts[k]
      const b = pts[k + 1]
      if (k % 2 === 1) segs.push([a, a, b, b])
      else {
        const dr = (b.r - a.r) * 0.5
        segs.push([a, { r: a.r + dr, c: a.c }, { r: b.r - dr, c: b.c }, b])
      }
    }
    let label: Etiqueta | null = null
    const li = etqDe[e]
    if (li >= 0) {
      const l = etq[li]
      const seg = segs[2 * (l.gap - vRank[s])] ?? segs[0]
      const libreIni = rankPos[l.gap] + rankSize[l.gap] + (hayGrupos ? GP : 0)
      const libreFin = rankPos[l.gap + 1] - (hayGrupos ? GP + (H ? 0 : GH) : 0)
      const objetivo = (libreIni + libreFin) / 2
      const c = enRank(seg, objetivo)
      const p = pos(objetivo, c)
      label = { lineas: l.lineas, w: l.w, h: l.h, x: p.x - l.w / 2, y: p.y - l.h / 2 }
      ;(label as Etiqueta & { gap: number; c0: number }).gap = l.gap
    }
    const ord = rev[e] ? [...segs].reverse().map((sg) => [...sg].reverse()) : segs
    const xy = (p: P) => pos(p.r, p.c)
    let d = ''
    ord.forEach((sg, k) => {
      const [a, b, c, z] = sg.map(xy)
      if (!k) d += `M${r1(a.x)},${r1(a.y)}`
      d += sg[0] === sg[1] && sg[2] === sg[3] ? `L${r1(z.x)},${r1(z.y)}` : `C${r1(b.x)},${r1(b.y)} ${r1(c.x)},${r1(c.y)} ${r1(z.x)},${r1(z.y)}`
    })
    const fin = rev[e] ? pts[0] : pts[pts.length - 1]
    const dir = rev[e] ? -1 : 1
    const tip = xy({ r: fin.r + dir * FL, c: fin.c })
    const dv = H ? { x: dir, y: 0 } : { x: 0, y: dir }
    return {
      key: `e${e}`,
      de: `n${ar.de}`,
      a: `n${ar.a}`,
      d,
      trazo: ar.trazo,
      punta: punta(tip.x, tip.y, dv.x, dv.y),
      etiqueta: label,
      num: '',
      numPos: null,
      titulo: ar.texto,
      detalle: '',
      datos: '',
      propia: false,
      rank: vRank[s],
    }
  })

  // labels sharing a gap are pushed apart along the cross axis
  const porGap = new Map<number, Etiqueta[]>()
  for (const a of aristas) {
    const l = a.etiqueta as (Etiqueta & { gap: number }) | null
    if (l) porGap.set(l.gap, [...(porGap.get(l.gap) ?? []), l])
  }
  for (const ls of porGap.values()) {
    const cOf = (l: Etiqueta) => (H ? l.y : l.x)
    const sz = (l: Etiqueta) => (H ? l.h : l.w)
    const set = (l: Etiqueta, v: number) => (H ? (l.y = v) : (l.x = v))
    ls.sort((a, b) => cOf(a) - cOf(b))
    // clusters of touching labels spread around their wanted middle instead of only drifting one way
    let ini = 0
    while (ini < ls.length) {
      const quiere = ls[ini]
      let fin = ini + 1
      let suma = cOf(quiere) + sz(quiere) / 2
      while (fin < ls.length && cOf(ls[fin]) < cOf(ls[fin - 1]) + sz(ls[fin - 1]) + 4) {
        suma += cOf(ls[fin]) + sz(ls[fin]) / 2
        set(ls[fin], cOf(ls[fin - 1]) + sz(ls[fin - 1]) + 4)
        fin++
      }
      if (fin - ini > 1) {
        const n = fin - ini
        const total = cOf(ls[fin - 1]) + sz(ls[fin - 1]) - cOf(ls[ini])
        const piso = ini > 0 ? cOf(ls[ini - 1]) + sz(ls[ini - 1]) + 4 : 4
        const corr = Math.max(piso, suma / n - total / 2) - cOf(ls[ini])
        for (let k = ini; k < fin; k++) set(ls[k], cOf(ls[k]) + corr)
      }
      ini = fin
    }
  }
  // then slide each group's own labels back inside its box
  for (const gr of grupos) {
    const gi = Number(gr.key.slice(1))
    const porSuGap = new Map<number, Etiqueta[]>()
    for (const a of aristas) {
      const l = a.etiqueta as (Etiqueta & { gap: number }) | null
      const n1 = g.nodos[Number(a.de.slice(1))]
      const n2 = g.nodos[Number(a.a.slice(1))]
      if (l && n1.grupo === gi && n2.grupo === gi) porSuGap.set(l.gap, [...(porSuGap.get(l.gap) ?? []), l])
    }
    const lo = (H ? gr.y : gr.x) + 6
    const hi = (H ? gr.y + gr.h : gr.x + gr.w) - 6
    for (const ls of porSuGap.values()) {
      const ini = Math.min(...ls.map((l) => (H ? l.y : l.x)))
      const fin = Math.max(...ls.map((l) => (H ? l.y + l.h : l.x + l.w)))
      const corr = fin - ini > hi - lo ? lo + (hi - lo) / 2 - (ini + fin) / 2 : ini < lo ? lo - ini : fin > hi ? hi - fin : 0
      if (corr) for (const l of ls) H ? (l.y += corr) : (l.x += corr)
    }
  }
  for (const a of aristas) {
    if (!a.etiqueta) continue
    const l = a.etiqueta as Etiqueta & { gap?: number }
    delete l.gap
    l.x = r1(l.x)
    l.y = r1(l.y)
  }

  let w = 0
  let h = 0
  for (const b of [...nodos, ...grupos, ...aristas.flatMap((a) => (a.etiqueta ? [a.etiqueta] : []))]) {
    w = Math.max(w, b.x + b.w)
    h = Math.max(h, b.y + b.h)
  }
  for (const a of aristas)
    for (const m of a.d.matchAll(/-?\d+(?:\.\d+)?,-?\d+(?:\.\d+)?/g)) {
      const [x, y] = m[0].split(',').map(Number)
      w = Math.max(w, x)
      h = Math.max(h, y)
    }
  return { tipo: op.tipo ?? 'diagrama', direccion: op.direccion, w: Math.ceil(w + M), h: Math.ceil(h + M), nodos, aristas, grupos, lineas: [], pasos: [] }
}

/** Cross coordinate where a rank-aligned cubic crosses `rk` (bisection; the curve is monotonic in rank). */
function enRank(seg: { r: number; c: number }[], rk: number): number {
  const [a, b, c, d] = seg
  const at = (t: number, k: 'r' | 'c') => {
    const u = 1 - t
    return u * u * u * a[k] + 3 * u * u * t * b[k] + 3 * u * t * t * c[k] + t * t * t * d[k]
  }
  const sube = d.r >= a.r
  let lo = 0
  let hi = 1
  for (let i = 0; i < 30; i++) {
    const mid = (lo + hi) / 2
    if (at(mid, 'r') < rk === sube) lo = mid
    else hi = mid
  }
  return at((lo + hi) / 2, 'c')
}

export function layoutDiagrama(d: DiagramaEstructura, op: OpLayout): Escena {
  return layoutGrafo(grafoDeDiagrama(d), { ...op, tipo: 'diagrama' })
}
