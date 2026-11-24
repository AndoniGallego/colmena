export type ModoNotch = 'cerrado' | 'panel' | 'aviso' | 'notas' | 'reunion' | 'guia'

export const UMBRAL_ARRASTRE = 5

export function superaUmbral(dx: number, dy: number): boolean {
  return Math.hypot(dx, dy) > UMBRAL_ARRASTRE
}

export const ANCHO_PANEL = 440
export const ANCHO_AVISO = 390
/** Modo notas: cabecera, campo y lista de notas. */
export const ANCHO_NOTAS = 420
export const RADIO_CERRADO = 22
export const RADIO_ABIERTO = 26
export const CASCADA_S = 0.05

export function morph(soft: boolean): { duration: number; ease: string } {
  return soft ? { duration: 0, ease: 'none' } : { duration: 0.6, ease: 'expo.out' }
}

export function anchoPara(modo: ModoNotch, cara: number, pantalla: number): number {
  if (modo === 'cerrado') return cara + 2
  const max = pantalla - 24
  if (modo === 'panel' || modo === 'reunion') return Math.min(ANCHO_PANEL, max)
  if (modo === 'notas' || modo === 'guia') return Math.min(ANCHO_NOTAS, max)
  return Math.min(ANCHO_AVISO, max)
}

/** Ancho de pastilla para el tamaño de ventana (siempre el modo abierto más ancho). */
export function anchoVentanaFijo(pantalla: number): number {
  return Math.max(anchoPara('panel', 0, pantalla), anchoPara('aviso', 0, pantalla), anchoPara('notas', 0, pantalla))
}

export function altoMax(pantallaAlto: number): number {
  return pantallaAlto - 70
}

/** Mantiene el cuerpo en DOM mientras la pastilla achica al cerrar. */
export function cuerpoVisible(modo: ModoNotch, cerrando: boolean): boolean {
  return modo !== 'cerrado' || cerrando
}

/** Evita que la cara cambie de estilo hasta terminar el cierre. */
export function pillAbierto(modo: ModoNotch, cerrando: boolean): boolean {
  return modo !== 'cerrado' || cerrando
}

export type TamanoVentana = { ancho: number; alto: number }

/** Pedido a puente().tamano cuando solo cambia foco (mismo tamaño de ventana). */
export function tamanoAlCambiarFoco(
  ultimo: TamanoVentana | null,
  foco: boolean,
): (TamanoVentana & { foco: boolean }) | null {
  if (!ultimo) return null
  return { ancho: ultimo.ancho, alto: ultimo.alto, foco }
}
