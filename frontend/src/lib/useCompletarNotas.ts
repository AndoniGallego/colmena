import { computed, getCurrentScope, onScopeDispose, reactive, ref } from 'vue'
import type { Nota } from '../api/types'

export const DESHACER_MS = 5000
export const ERR_HECHA = 'No pude marcarla. Probá de nuevo.'
export const ERR_DESHACER = 'No pude deshacerlo. Probá de nuevo.'

interface Hecha {
  nota: Nota
  indice: number
}

/**
 * Completar y deshacer notas del notch. Una nota recién completada sigue visible (con Deshacer)
 * durante DESHACER_MS aunque el servidor ya no la liste, en el lugar que ocupaba.
 */
export function useCompletarNotas(o: {
  base: () => Nota[]
  marcar: (id: string, hecha: boolean) => Promise<void>
  tope: number
}) {
  const hechas = reactive(new Map<string, Hecha>())
  const enVuelo = new Set<string>()
  /** Deshacer tocado mientras el pedido de marcar sigue en vuelo: se aplica cuando termina. */
  const deshacerPendiente = new Set<string>()
  /** Notas con el pedido de marcar hecha en vuelo (no el de deshacer). */
  const marcando = new Set<string>()
  const timers = new Map<string, ReturnType<typeof setTimeout>>()
  const error = ref('')

  const visibles = computed(() => {
    const lista = o.base().slice()
    const pegadas = [...hechas.values()].sort((a, b) => a.indice - b.indice)
    for (const { nota, indice } of pegadas) {
      if (!lista.some((n) => n.id === nota.id)) lista.splice(Math.min(indice, lista.length), 0, nota)
    }
    return lista.slice(0, o.tope)
  })

  const esHecha = (id: string) => hechas.has(id)

  function soltar(id: string) {
    clearTimeout(timers.get(id))
    timers.delete(id)
    hechas.delete(id)
    deshacerPendiente.delete(id)
  }

  async function completar(n: Nota) {
    if (enVuelo.has(n.id)) return
    enVuelo.add(n.id)
    marcando.add(n.id)
    error.value = ''
    hechas.set(n.id, { nota: n, indice: visibles.value.findIndex((c) => c.id === n.id) })
    let deshacerAhora = false
    try {
      await o.marcar(n.id, true)
      deshacerAhora = deshacerPendiente.delete(n.id)
      if (!deshacerAhora) timers.set(n.id, setTimeout(() => soltar(n.id), DESHACER_MS))
    } catch {
      deshacerPendiente.delete(n.id)
      soltar(n.id)
      error.value = ERR_HECHA
    } finally {
      enVuelo.delete(n.id)
      marcando.delete(n.id)
    }
    if (deshacerAhora) await deshacer(n.id)
  }

  async function deshacer(id: string) {
    if (!hechas.has(id)) return
    if (marcando.has(id)) {
      deshacerPendiente.add(id)
      return
    }
    if (enVuelo.has(id)) return
    enVuelo.add(id)
    error.value = ''
    clearTimeout(timers.get(id))
    try {
      await o.marcar(id, false)
      soltar(id)
    } catch {
      error.value = ERR_DESHACER
      timers.set(id, setTimeout(() => soltar(id), DESHACER_MS))
    } finally {
      enVuelo.delete(id)
    }
  }

  if (getCurrentScope()) {
    onScopeDispose(() => {
      for (const t of timers.values()) clearTimeout(t)
      timers.clear()
    })
  }

  return { visibles, error, esHecha, completar, deshacer }
}
