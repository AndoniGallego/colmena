import { computed, shallowRef } from 'vue'
import { esTerminalPropia } from '../lib/terminalPropia'
import { loadTerminalConfig, tconfig } from './terminalActions'

export const vivoAbierto = shallowRef<{ paneId: string; titulo: string } | null>(null)

export const vivoHabilitado = computed(() => tconfig.value?.vivo === true)

let pedirPinAlAbrir = false

export function abrirVivo(paneId: string, titulo: string, opts?: { pedirPin?: boolean }): void {
  if (!esTerminalPropia(paneId)) return
  pedirPinAlAbrir = opts?.pedirPin === true
  vivoAbierto.value = { paneId, titulo }
}

/** Una sola vez tras abrir TerminalVivo: indica si hay que mostrar el PIN al montar. */
export function consumirPedirPinAlAbrir(): boolean {
  const v = pedirPinAlAbrir
  pedirPinAlAbrir = false
  return v
}

export function cerrarVivo(): void {
  vivoAbierto.value = null
}

export { loadTerminalConfig }
