const UMBRAL_MS = 3000

export function mostrarFranja(
  conn: 'live' | 'connecting' | 'reconnecting',
  desdeMs: number | null,
  ahoraMs: number,
): boolean {
  if (conn === 'live') return false
  if (desdeMs === null) return false
  return ahoraMs - desdeMs >= UMBRAL_MS
}
