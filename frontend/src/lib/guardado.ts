import type { Guardado, GuardadoPane, GuardadoTarget } from '../api/types'

const PANE: Record<GuardadoPane['estado'], string> = {
  guardando: 'guardando en Engram',
  listo: 'ya guardó',
  bloqueado: 'esperando tu respuesta',
  fallo: 'no pude pedirle que guarde',
}

export const paneEstadoLabel = (e: GuardadoPane['estado']): string => PANE[e] ?? e

const TARGET: Record<GuardadoTarget['estado'], string> = {
  guardando: 'guardando',
  cerrando: 'cerrando',
  cerrado: 'cerrado',
  error: 'revisar de nuevo',
  cancelado: 'cancelado',
}

export const targetEstadoLabel = (e: GuardadoTarget['estado']): string => TARGET[e] ?? e

const AUDITORIA: Record<string, string> = { ok: 'guardó', saltado: 'sin guardar', vencido: 'cerrado sin esperar' }
export const guardadoLabel = (g: string): string => AUDITORIA[g] ?? ''

/** Lo que la barra de espera le dice al usuario según el estado del lote. */
export function leyenda(g: Guardado): string {
  if (g.terminado) return 'Listo'
  if (g.vencido) return 'Pasaron 5 minutos y todavía no terminan de guardar. No cierro solo.'
  if (g.targets.some((t) => t.panes.some((p) => p.estado === 'bloqueado'))) return 'Alguna sesión espera tu respuesta antes de seguir.'
  return 'Les pedí que guarden lo importante en Engram. Cierro cuando terminen.'
}

/** Con una sesión esperando respuesta, que falló o con el tiempo vencido el usuario puede cerrar igual o esperar más. */
export const puedeEsperarMas = (g: Guardado): boolean => g.vencido && !g.terminado
