/** Si el evento viene de un campo editable, los atajos del notch no deben interceptar la tecla. */
export function esCampoTextoNotch(target: EventTarget | null): boolean {
  const el = target instanceof HTMLElement ? target : null
  if (!el) return false
  if (el.isContentEditable) return true
  const tag = el.tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return true
  return !!el.closest('input, textarea, select, [contenteditable=""], [contenteditable="true"]')
}
