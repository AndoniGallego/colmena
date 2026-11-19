/** ¿El puntero se alejó más de px desde el punto inicial? (comparación euclídea, sin sqrt). */
export function superaUmbral(x0: number, y0: number, x: number, y: number, px = 8): boolean {
  const dx = x - x0
  const dy = y - y0
  return dx * dx + dy * dy > px * px
}
