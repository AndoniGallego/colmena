export function estaALaVista(
  doc: Pick<Document, 'visibilityState' | 'hasFocus'> | undefined,
  escritorio: boolean,
): boolean {
  if (!doc) return true
  if (doc.visibilityState !== 'visible') return false
  return escritorio ? doc.hasFocus() : true
}
