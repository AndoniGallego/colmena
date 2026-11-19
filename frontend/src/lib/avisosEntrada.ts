/** Id más alto conocido tras un refresco, para marcar leído sin carreras con otro fetch. */
export function hastaMarcarLeido(leidosHasta: number, items: { id: number }[]): number {
  return Math.max(leidosHasta, 0, ...items.map((a) => a.id))
}
