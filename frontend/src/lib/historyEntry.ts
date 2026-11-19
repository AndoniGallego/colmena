/**
 * Una entrada de historial propia para una vista de detalle en el celu: así el botón Atrás
 * del navegador y el gesto de volver la cierran. `onBack` corre cuando la entrada se va (popstate).
 */
export function historyEntry(key: string, onBack: () => void) {
  let pushed = false
  const ours = () => {
    const s = history.state as Record<string, unknown> | null
    return !!s && s[key] !== undefined && s[key] !== null && s[key] !== false
  }
  window.addEventListener('popstate', () => {
    if (pushed && !ours()) {
      pushed = false
      onBack()
    }
  })
  return {
    get pushed() {
      return pushed
    },
    /** Abre (o reemplaza, si ya hay una) la entrada con `value`. */
    push(value: unknown) {
      const state = { ...((history.state as object | null) ?? {}), [key]: value }
      if (pushed && ours()) history.replaceState(state, '')
      else {
        history.pushState(state, '')
        pushed = true
      }
    },
    /** Saca la entrada si es nuestra: devuelve true y el cierre llega por `onBack`. */
    back(): boolean {
      if (pushed && ours()) {
        history.back()
        return true
      }
      pushed = false
      return false
    },
  }
}
