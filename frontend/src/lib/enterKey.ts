export type EnterMode = 'send' | 'stop'

export interface EnterKeyInput {
  mode: EnterMode
  disabled?: boolean
  busy?: boolean
  label?: string
  stopLabel?: string
}

export function enterKeyState(p: EnterKeyInput) {
  const stop = p.mode === 'stop'
  return {
    type: stop ? ('button' as const) : ('submit' as const),
    label: stop ? (p.stopLabel ?? 'Detener') : (p.label ?? 'Enviar'),
    disabled: !!p.disabled,
    glyph: p.busy ? ('spin' as const) : stop ? ('stop' as const) : ('enter' as const),
  }
}

export interface LBox {
  x0: number
  y0: number
  x1: number
  y1: number
  wingY: number
  stemX: number
  r: number
  rc: number
}

const n = (v: number) => Math.round(v * 100) / 100

// L de la tecla ISO: ala arriba a todo el ancho y tallo a la derecha hasta abajo; la esquina interior es cóncava.
export function lPath(b: LBox) {
  const r = Math.max(0, Math.min(b.r, (b.wingY - b.y0) / 2, (b.x1 - b.stemX) / 2))
  const rc = Math.max(0, Math.min(b.rc, b.stemX - b.x0 - r, b.y1 - b.wingY - r))
  return [
    `M${n(b.x0 + r)} ${n(b.y0)}`,
    `H${n(b.x1 - r)}A${n(r)} ${n(r)} 0 0 1 ${n(b.x1)} ${n(b.y0 + r)}`,
    `V${n(b.y1 - r)}A${n(r)} ${n(r)} 0 0 1 ${n(b.x1 - r)} ${n(b.y1)}`,
    `H${n(b.stemX + r)}A${n(r)} ${n(r)} 0 0 1 ${n(b.stemX)} ${n(b.y1 - r)}`,
    `V${n(b.wingY + rc)}A${n(rc)} ${n(rc)} 0 0 0 ${n(b.stemX - rc)} ${n(b.wingY)}`,
    `H${n(b.x0 + r)}A${n(r)} ${n(r)} 0 0 1 ${n(b.x0)} ${n(b.wingY - r)}`,
    `V${n(b.y0 + r)}A${n(r)} ${n(r)} 0 0 1 ${n(b.x0 + r)} ${n(b.y0)}Z`,
  ].join('')
}

export interface KeyGeom {
  w: number
  h: number
  wing: number
  stem: number
  r: number
  depth: number
  bevel: number
}

// Capas de la tecla: falda (profundidad), cuerpo (bisel) y cara; el bisel de abajo es más grueso, como vista desde arriba.
export function keyShapes(g: KeyGeom) {
  const { w, h, wing, stem, r, depth: d, bevel: b } = g
  const stemX = w - stem
  const top = h - d
  const fb = b * 1.7
  return {
    skirt: lPath({ x0: 0, y0: d, x1: w, y1: h, wingY: wing + d, stemX, r, rc: r * 0.7 }),
    body: lPath({ x0: 0, y0: 0, x1: w, y1: top, wingY: wing, stemX, r, rc: r * 0.7 }),
    face: lPath({ x0: b, y0: b * 0.6, x1: w - b, y1: top - fb, wingY: wing - fb, stemX: stemX + b, r: r - b * 0.8, rc: r * 0.7 + fb }),
    ring: lPath({ x0: -3.5, y0: -3.5, x1: w + 3.5, y1: h + 3.5, wingY: wing + d + 3.5, stemX: stemX - 3.5, r: r + 3.5, rc: Math.max(0, r * 0.7 - 3.5) }),
    glyph: { x: stemX + stem / 2, y: (b * 0.6 + top - fb) / 2 },
  }
}
