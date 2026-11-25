import { ref } from 'vue'
import { EDITABLES, etiquetaCombo, partesCombo, type Combo } from '../lib/teclas'

/** Solo lo que el usuario cambió: id -> combinación. Lo que falta usa el original. */
export const atajosGuardados = ref<Record<string, Combo>>({})
export const atajosError = ref('')
/** Mientras se captura una combinación nueva, los demás atajos no se disparan. */
export const capturandoAtajo = ref(false)

export function comboDe(id: string): Combo {
  return atajosGuardados.value[id] ?? EDITABLES.find((a) => a.id === id)?.original ?? ''
}

export const etiquetaDe = (id: string, mac?: boolean): string => etiquetaCombo(comboDe(id), mac)
export const partesDe = (id: string, mac?: boolean): string[] => partesCombo(comboDe(id), mac)

export function efectivos(): Record<string, Combo> {
  return Object.fromEntries(EDITABLES.map((a) => [a.id, comboDe(a.id)]))
}
