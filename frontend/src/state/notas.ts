import { ref, shallowRef, watch } from 'vue'
import type { Nota, TipoNota, OrigenNota } from '../api/types'
import { boardState, borrarNotaApi, crearNotaApi, editarNotaApi, listarNotas } from './app'

export const notas = shallowRef<Nota[]>([])
export const pendientes = ref(0)
/** Pestaña visible (pager móvil o capa de escritorio). */
export const notasVisible = ref(false)
/** Pedido de saltar al mensaje de una sesión desde una nota con origen. */
export const saltoMensaje = ref<{ sid: string; ts: string } | null>(null)

let ultimaVersion = -1
let secuencia = 0

export async function cargarNotas(): Promise<void> {
  const mia = ++secuencia
  try {
    const r = await listarNotas()
    if (mia !== secuencia) return
    notas.value = [...r.notas].sort((a, b) => b.creada_at.localeCompare(a.creada_at))
    pendientes.value = r.pendientes
    ultimaVersion = r.version
  } catch {
    // Las notas nunca rompen el tablero: queda el estado anterior.
  }
}

// La versión del servidor vuelve a 0 con cada reinicio y lo que cambió sin conexión no llega como evento: al reconectar se olvida y se recarga.
watch(
  () => boardState.value.connection,
  (ahora, antes) => {
    if (ahora === 'live' && antes !== 'live') {
      ultimaVersion = -1
      void cargarNotas()
    }
  },
)

export function onNotas(d: { version: number; pendientes: number }): void {
  if (d.version === ultimaVersion) return
  void cargarNotas()
}

export async function crearNota(b: { tipo: TipoNota; texto: string; origen?: OrigenNota }): Promise<void> {
  await crearNotaApi(b)
  await cargarNotas()
}

export async function editarNota(id: string, b: { texto?: string; tipo?: TipoNota; hecha?: boolean }): Promise<void> {
  await editarNotaApi(id, b)
  await cargarNotas()
}

export async function borrarNota(id: string): Promise<void> {
  await borrarNotaApi(id)
  await cargarNotas()
}

export const marcarHecha = (id: string, hecha: boolean): Promise<void> => editarNota(id, { hecha })
