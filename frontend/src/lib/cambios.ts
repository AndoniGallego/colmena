/** Índice del archivo seleccionado tras moverse `delta`, sin salirse de la lista; -1 es "ninguno". */
export function mover(actual: number, delta: number, total: number): number {
  if (total <= 0) return -1
  if (actual < 0) return delta > 0 ? 0 : total - 1
  return Math.min(total - 1, Math.max(0, actual + delta))
}

export function teclaMovimiento(key: string): number {
  if (key === 'j' || key === 'ArrowDown') return 1
  if (key === 'k' || key === 'ArrowUp') return -1
  return 0
}
