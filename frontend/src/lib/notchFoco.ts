import type { ModoNotch } from './notchMovimiento'
import type { AvisoNotch } from './notchAvisos'

export type AccionFocoNotch =
  | { tipo: 'alternar'; eraPanel: boolean }
  | { tipo: 'esc' }
  | { tipo: 'blur' }
  | { tipo: 'aviso_tocado' }
  | { tipo: 'modo_cambio'; modo: ModoNotch }
  | { tipo: 'aviso_cambio'; clave: string | null; claveAnterior: string | null }

export function debeCerrarPanelAlPerderFoco(modo: ModoNotch): boolean {
  return modo === 'panel' || modo === 'reunion'
}

/**
 * En Windows, darle el teclado a la página (MoveFocus de WebView2) dispara un `blur` pasajero de la ventana.
 * Antes de cerrar se espera este rato y se confirma que el foco se fue de verdad.
 */
export const GRACIA_BLUR_MS = 150

/** Durante una reunión en curso la vista queda a la vista para ir siguiendo las preguntas: la cierra Ando. */
export function cerrarTrasBlur(modo: ModoNotch, tieneFoco: boolean, reunionEnCurso = false): boolean {
  if (modo === 'reunion' && reunionEnCurso) return false
  return !tieneFoco && debeCerrarPanelAlPerderFoco(modo)
}

export function claveAvisoNotch(aviso: AvisoNotch | null | undefined): string | null {
  if (!aviso) return null
  return `${aviso.id}:${aviso.session_id}`
}

export function reducirFocoNotch(foco: boolean, accion: AccionFocoNotch): boolean {
  switch (accion.tipo) {
    case 'alternar':
      return accion.eraPanel ? false : true
    case 'esc':
    case 'blur':
      return false
    case 'aviso_tocado':
      return true
    case 'modo_cambio':
      if (accion.modo === 'cerrado') return false
      return accion.modo === 'notas' || accion.modo === 'guia' ? true : foco
    case 'aviso_cambio':
      return accion.clave === accion.claveAnterior ? foco : false
    default:
      return foco
  }
}
