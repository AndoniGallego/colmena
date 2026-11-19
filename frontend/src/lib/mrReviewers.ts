export type MrPersonaMin = { username: string }

/** Usernames elegibles para persistir; null si el equipo no está listo (evita mandar []). */
export function reviewersParaGuardar(equipo: readonly MrPersonaMin[], elegidos: Iterable<string>, equipoListo: boolean): string[] | null {
  if (!equipoListo || equipo.length === 0) return null
  const permitidos = new Set(equipo.map((e) => e.username))
  return [...elegidos].filter((u) => permitidos.has(u))
}

export function elegidosDesdeReviewers(reviewers: readonly MrPersonaMin[], equipo: readonly MrPersonaMin[]): Set<string> {
  const ok = new Set(equipo.map((e) => e.username))
  return new Set(reviewers.map((r) => r.username).filter((u) => ok.has(u)))
}
