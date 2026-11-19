import { debeAbrirTerminalLocal } from '../lib/abrirTerminalCliente'

export interface AbrirTerminalPayload {
  pane_id: string
  titulo: string
}

export function manejarAbrirTerminalSse(
  payload: AbrirTerminalPayload,
  ctx: { presenciaActiva: boolean; esEscritorio: boolean },
  abrir: (paneId: string, titulo: string) => void,
): void {
  if (!debeAbrirTerminalLocal(ctx)) return
  abrir(payload.pane_id, payload.titulo)
}
