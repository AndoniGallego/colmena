import type { ModoNotch } from './notchMovimiento'

export type AccionToqueNotch = 'alternar' | 'mostrar_ventana'

const VIVAS: readonly string[] = ['escuchando', 'pausada', 'sin_pc', 'llena']

/** La reunión sigue viva (escucha, está en pausa o falta guardarla): la sigue la ventana "Reunión". */
export function reunionViva(estado: string): boolean {
  return VIVAS.includes(estado)
}

/** Qué hace tocar el notch: con una reunión viva y el notch cerrado, trae la ventana "Reunión" (solo en la app de Windows). */
export function accionAlTocarNotch(o: { modo: ModoNotch; estadoReunion: string; enPrograma: boolean }): AccionToqueNotch {
  return o.enPrograma && o.modo === 'cerrado' && reunionViva(o.estadoReunion) ? 'mostrar_ventana' : 'alternar'
}
