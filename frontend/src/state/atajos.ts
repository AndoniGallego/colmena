import { watch } from 'vue'
import { ApiError } from '../api/types'
import { EDITABLES, type Combo } from '../lib/teclas'
import { auth, getAtajos, setAtajos } from './app'
import { atajosError, atajosGuardados } from './atajosEstado'

export { atajosError, atajosGuardados, capturandoAtajo, comboDe, efectivos, etiquetaDe, partesDe } from './atajosEstado'

function limpiar(raw: unknown): Record<string, Combo> {
  const out: Record<string, Combo> = {}
  if (!raw || typeof raw !== 'object') return out
  for (const [id, combo] of Object.entries(raw as Record<string, unknown>)) {
    const a = EDITABLES.find((x) => x.id === id)
    if (a && typeof combo === 'string' && combo && combo !== a.original) out[id] = combo
  }
  return out
}

export async function cargarAtajos(): Promise<void> {
  try {
    atajosGuardados.value = limpiar(await getAtajos())
  } catch {
    /* quedan los originales */
  }
}

async function guardar(next: Record<string, Combo>): Promise<boolean> {
  const prev = atajosGuardados.value
  atajosGuardados.value = next
  atajosError.value = ''
  try {
    await setAtajos(next)
    return true
  } catch (e) {
    atajosGuardados.value = prev
    if (!(e instanceof ApiError && e.status === 401)) atajosError.value = 'No pude guardar el atajo'
    return false
  }
}

export function cambiarAtajo(id: string, combo: Combo): Promise<boolean> {
  return guardar(limpiar({ ...atajosGuardados.value, [id]: combo }))
}

export function restaurarAtajo(id: string): Promise<boolean> {
  const { [id]: _quitado, ...resto } = atajosGuardados.value
  return guardar(resto)
}

let started = false
export function initAtajos(): void {
  if (started) return
  started = true
  watch(() => auth.value, (a) => a === 'ready' && void cargarAtajos(), { immediate: true })
}
