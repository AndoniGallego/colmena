import { reactive, watch } from 'vue'
import type { PedidoPermiso } from '../api/types'
import { auth, getPermisos } from './app'

const ABIERTO = new Set(['abierto', 'enviando'])

export const pedidosAbiertos = reactive<PedidoPermiso[]>([])

export function actualizarPedidos(pedidos: PedidoPermiso[]) {
  const abiertos = pedidos.filter((p) => ABIERTO.has(p.estado))
  pedidosAbiertos.splice(0, pedidosAbiertos.length, ...abiertos)
}

export async function refrescarPermisos(): Promise<void> {
  try {
    const r = await getPermisos()
    actualizarPedidos(r.pedidos)
  } catch {
    /* el SSE vuelve a sincronizar */
  }
}

if (import.meta.env?.MODE !== 'test') {
  watch(() => auth.value, (a) => a === 'ready' && void refrescarPermisos(), { immediate: true })
}
