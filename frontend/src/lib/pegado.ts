/**
 * Qué hacer cuando cambia de tamaño el hilo o el visor. Pegado al fondo: volver al fondo (el composer que crece
 * achica el visor y si no, lo último queda tapado). Scrolleado arriba: no mover nada; solo el contenido nuevo
 * ofrece "Ir al final", un visor que cambia de alto no.
 */
export function resizeAction(stick: boolean, targets: readonly unknown[], content: unknown): 'bottom' | 'jump' | null {
  if (stick) return 'bottom'
  return content != null && targets.includes(content) ? 'jump' : null
}
