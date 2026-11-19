// Geometría y marca de Colmena. Sin dependencias: lo usan los componentes y tools/iconos.mjs.

export type LogoVariant = 'panal' | 'abeja' | 'monograma'

export const LOGO_VARIANTS: readonly LogoVariant[] = ['panal', 'abeja', 'monograma']
export const DEFAULT_LOGO: LogoVariant = 'panal'

export const LOGO_INFO: Record<LogoVariant, { nombre: string; desc: string }> = {
  panal: { nombre: 'Panal', desc: 'Siete celdas; se encienden las de las sesiones que trabajan.' },
  abeja: { nombre: 'Abeja', desc: 'Una celda grande que una abeja recorre mientras hay trabajo.' },
  monograma: { nombre: 'Monograma', desc: 'Una C de celdas con la abeja en la abertura.' },
}

export const isLogoVariant = (v: unknown): v is LogoVariant => typeof v === 'string' && (LOGO_VARIANTS as readonly string[]).includes(v)

export interface Pt {
  x: number
  y: number
}
export interface Cell extends Pt {
  d: string
}

const f = (n: number) => +n.toFixed(2)
const SQ3 = Math.sqrt(3)

/** Vértices de un hexágono con punta arriba. */
export function hexPoints(cx: number, cy: number, r: number): Pt[] {
  return Array.from({ length: 6 }, (_, i) => {
    const a = ((-90 + 60 * i) * Math.PI) / 180
    return { x: cx + r * Math.cos(a), y: cy + r * Math.sin(a) }
  })
}

/** Hexágono con punta arriba y esquinas redondeadas (`round` = distancia del corte en cada vértice). */
export function hexPath(cx: number, cy: number, r: number, round = r * 0.2): string {
  const v = hexPoints(cx, cy, r)
  const k = Math.min(0.5, round / r)
  const lerp = (a: Pt, b: Pt, t: number) => ({ x: a.x + (b.x - a.x) * t, y: a.y + (b.y - a.y) * t })
  let d = ''
  v.forEach((p, i) => {
    const prev = v[(i + 5) % 6]
    const next = v[(i + 1) % 6]
    const a = lerp(p, prev, k)
    const b = lerp(p, next, k)
    d += `${i ? 'L' : 'M'}${f(a.x)} ${f(a.y)}Q${f(p.x)} ${f(p.y)} ${f(b.x)} ${f(b.y)}`
  })
  return `${d}Z`
}

/** Polígono hexagonal abierto que recorre `laps` vueltas en sentido horario desde el vértice `from`. */
export function hexTrack(cx: number, cy: number, r: number, from = 1, laps = 1): string {
  const v = hexPoints(cx, cy, r)
  const pts = Array.from({ length: 6 * laps + 1 }, (_, i) => v[(from + i) % 6])
  return pts.map((p, i) => `${i ? 'L' : 'M'}${f(p.x)} ${f(p.y)}`).join('')
}

/** Centro de una celda en coordenadas axiales de una grilla de hexágonos con punta arriba. */
export function axial(q: number, r: number, step: number, c = 32): Pt {
  return { x: c + step * (q + r / 2), y: c + step * (SQ3 / 2) * r }
}

const cell = (p: Pt, r: number, round?: number): Cell => ({ ...p, d: hexPath(p.x, p.y, r, round) })

// ---------- Panal: centro + anillo de 6 ----------
export interface PanalGeo {
  center: Cell
  /** En sentido horario desde arriba a la derecha: el orden en que se encienden. */
  ring: Cell[]
  r: number
}
export function panalGeo(gap = 2.6, r = 10.2): PanalGeo {
  const step = SQ3 * r + gap
  const order: [number, number][] = [[1, -1], [1, 0], [0, 1], [-1, 1], [-1, 0], [0, -1]]
  return { center: cell(axial(0, 0, step), r), ring: order.map(([q, s]) => cell(axial(q, s, step), r)), r }
}

// ---------- Abeja: celda grande + núcleo + abeja en un vértice ----------
export const ABEJA = { cx: 32, cy: 32, r: 21.5, stroke: 7, core: 7.4, bee: 6.2, home: 1 } as const
export function abejaGeo() {
  const { cx, cy, r, core, home } = ABEJA
  const v = hexPoints(cx, cy, r)
  return {
    ring: hexTrack(cx, cy, r, 0, 1) + 'Z',
    track: hexTrack(cx, cy, r, home, 1),
    trail: hexTrack(cx, cy, r, home, 2),
    core: hexPath(cx, cy, core, core * 0.22),
    bee: v[home],
  }
}

// ---------- Monograma: C de 9 celdas + abeja en la abertura ----------
export interface MonoGeo {
  /** De la punta de arriba a la de abajo, recorriendo la C. */
  arc: Cell[]
  bee: Cell
  r: number
}
export function monoGeo(gap = 1.7, r = 6.15): MonoGeo {
  const step = SQ3 * r + gap
  const order: [number, number][] = [[2, -2], [1, -2], [0, -2], [-1, -1], [-2, 0], [-2, 1], [-2, 2], [-1, 2], [0, 2]]
  const shift = -step * 0.25
  const arc = order.map(([q, s]) => {
    const p = axial(q, s, step)
    return cell({ x: p.x + shift, y: p.y }, r)
  })
  const b = axial(2, 0, step)
  return { arc, bee: cell({ x: b.x + shift - step * 0.08, y: b.y }, r * 1.02), r }
}

// ---------- Íconos estáticos (PWA, favicon) ----------
export interface IconPalette {
  bg: [string, string, string]
  ink: string
  lit: string
  dim: string
  glow: string
}
export const ICON_PALETTE: IconPalette = {
  bg: ['#1b211d', '#101412', '#090b0a'],
  ink: '#e9e7df',
  lit: '#c6f25e',
  dim: 'rgba(233,231,223,0.16)',
  glow: '#c6f25e',
}

export interface IconOpts {
  /** Tamaño de salida en px, sólo para ajustar trazos finos en tamaños chicos. */
  px?: number
  /** Radio de las esquinas del fondo sobre 512 (0 = sangrado completo, para maskable/apple). */
  radius?: number
  /** Escala del logo dentro del cuadro (maskable usa zona segura). */
  scale?: number
  palette?: IconPalette
}

/** Celdas encendidas en el ícono: tres vecinas arriba a la derecha y una suelta abajo. */
const ICON_LIT = [0, 1, 3]

function markSvg(v: LogoVariant, px: number, p: IconPalette): string {
  const small = px <= 48
  if (v === 'panal') {
    const g = panalGeo(small ? 4.4 : 2.6, small ? 10.6 : 10.2)
    const ring = g.ring
      .map((c, i) => `<path d="${c.d}" fill="${ICON_LIT.includes(i) ? p.lit : p.dim}"/>`)
      .join('')
    return `<path d="${g.center.d}" fill="${p.ink}"/>${ring}`
  }
  if (v === 'abeja') {
    const g = abejaGeo()
    const sw = small ? ABEJA.stroke + 1.5 : ABEJA.stroke
    return (
      `<path d="${g.ring}" fill="none" stroke="${p.ink}" stroke-width="${sw}" stroke-linejoin="round"/>` +
      `<path d="${g.core}" fill="${p.ink}"/>` +
      `<circle cx="${f(g.bee.x)}" cy="${f(g.bee.y)}" r="${ABEJA.bee + (small ? 1 : 0)}" fill="${p.lit}" stroke="#101412" stroke-width="${small ? 4 : 3.2}" paint-order="stroke"/>`
    )
  }
  const g = monoGeo(small ? 2.6 : 1.7, small ? 6 : 6.15)
  return g.arc.map((c) => `<path d="${c.d}" fill="${p.ink}"/>`).join('') + `<path d="${g.bee.d}" fill="${p.lit}"/>`
}

/** SVG completo de un ícono de app 512×512 para la variante. */
export function iconSvg(v: LogoVariant, o: IconOpts = {}): string {
  const p = o.palette ?? ICON_PALETTE
  const px = o.px ?? 512
  const radius = o.radius ?? 114
  const scale = o.scale ?? (px <= 48 ? 7.4 : 6.6)
  const off = f(256 - 32 * scale)
  const glowAt = v === 'panal' ? { x: 340, y: 190 } : v === 'abeja' ? { x: 360, y: 150 } : { x: 380, y: 256 }
  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="${px}" height="${px}"><defs>` +
    `<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${p.bg[0]}"/><stop offset=".55" stop-color="${p.bg[1]}"/><stop offset="1" stop-color="${p.bg[2]}"/></linearGradient>` +
    `<radialGradient id="gl" gradientUnits="userSpaceOnUse" cx="${glowAt.x}" cy="${glowAt.y}" r="230"><stop offset="0" stop-color="${p.glow}" stop-opacity="0.24"/><stop offset=".5" stop-color="${p.glow}" stop-opacity="0.06"/><stop offset="1" stop-color="${p.glow}" stop-opacity="0"/></radialGradient>` +
    `<radialGradient id="vg" cx=".5" cy="0" r="1"><stop offset="0" stop-color="#fff" stop-opacity="0.06"/><stop offset=".6" stop-color="#fff" stop-opacity="0"/></radialGradient>` +
    `<clipPath id="cl"><rect width="512" height="512" rx="${radius}"/></clipPath></defs>` +
    `<g clip-path="url(#cl)"><rect width="512" height="512" fill="url(#bg)"/><rect width="512" height="512" fill="url(#vg)"/>` +
    (px > 48 ? `<rect width="512" height="512" fill="url(#gl)"/>` : '') +
    `<g transform="translate(${off} ${off}) scale(${scale})">${markSvg(v, px, p)}</g>` +
    (radius && px > 48 ? `<rect x="1.5" y="1.5" width="509" height="509" rx="${radius - 1.5}" fill="none" stroke="#fff" stroke-opacity="0.08" stroke-width="3"/>` : '') +
    `</g></svg>`
  )
}
