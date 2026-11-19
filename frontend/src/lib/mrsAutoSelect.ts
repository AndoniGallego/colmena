/** En escritorio, si la lista ya cargó y no hay MR elegido, abrir el primero visible. */
export function mrsAutoSelectRef(input: {
  desktop: boolean
  loaded: boolean
  selected: string | null
  visibleRefs: readonly string[]
}): string | null {
  if (!input.desktop || !input.loaded || input.selected) return null
  return input.visibleRefs[0] ?? null
}
