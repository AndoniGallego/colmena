export type FotoRef = { id: string }

export type GridCell = { index: number; span?: 'large' }

/** Celdas visibles en la miniatura (máx 4), estilo WhatsApp. */
export function gridLayout(count: number): GridCell[] {
  if (count <= 0) return []
  if (count === 1) return [{ index: 0 }]
  if (count === 2) return [{ index: 0 }, { index: 1 }]
  if (count === 3) return [{ index: 0, span: 'large' }, { index: 1 }, { index: 2 }]
  return [{ index: 0 }, { index: 1 }, { index: 2 }, { index: 3 }]
}

export function overlayExtra(count: number): number {
  return count > 4 ? count - 3 : 0
}

export function stepIndex(current: number, delta: number, total: number): number {
  if (total <= 0) return 0
  const next = current + delta
  if (next < 0) return 0
  if (next >= total) return total - 1
  return next
}
