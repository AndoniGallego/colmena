export type MobileView = 'board' | 'mrs' | 'notas' | 'biblioteca' | (string & {})

/** Orden de tabs en celu; sin MRs si no están habilitados. Las secciones extra van después de MRs y antes de Notas. */
export function mobilePageOrder(mrsHabilitado: boolean, extras: { id: string }[] = []): MobileView[] {
  return ['board', ...(mrsHabilitado ? ['mrs'] : []), ...extras.map((e) => e.id), 'notas', 'biblioteca']
}

export function mobilePageIndex(order: MobileView[], view: MobileView): number {
  const i = order.indexOf(view)
  return i >= 0 ? i : 0
}
