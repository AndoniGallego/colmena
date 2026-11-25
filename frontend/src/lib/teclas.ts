/**
 * Atajos que se pueden cambiar. Combinación: `[mod+][alt+][shift+]tecla`, en minúsculas.
 * `mod` es Ctrl en Windows y Linux, ⌘ en Mac. Debe coincidir con backend/orquestador/atajos.py.
 */
export type Combo = string

export interface AtajoEditable {
  id: string
  que: string
  original: Combo
  /** Dos atajos chocan si tienen la misma combinación y alguno es global o comparten ámbito. */
  ambito: string
  /** Puede ser una tecla sola, sin Ctrl/Alt/Shift. */
  sinModificador?: boolean
}

export const EDITABLES: AtajoEditable[] = [
  { id: 'buscador', que: 'Abrir el buscador', original: 'mod+k', ambito: 'global' },
  { id: 'dictar', que: 'Dictar por voz', original: 'mod+shift+space', ambito: 'global' },
  { id: 'minimizar-preguntas', que: 'Minimizar las preguntas', original: 'm', ambito: 'preguntas', sinModificador: true },
  { id: 'crear-terminal', que: 'Crear la terminal', original: 'mod+enter', ambito: 'terminal' },
  { id: 'comentar', que: 'Agregar el comentario', original: 'mod+enter', ambito: 'cambios' },
]

export interface TeclaLike {
  key: string
  code?: string
  ctrlKey?: boolean
  metaKey?: boolean
  altKey?: boolean
  shiftKey?: boolean
}

export function esMac(): boolean {
  return typeof navigator !== 'undefined' && /mac|iphone|ipad/i.test(navigator.platform || navigator.userAgent || '')
}

const SOLO_MODIFICADOR = new Set(['control', 'shift', 'alt', 'meta', 'altgraph', 'capslock', 'os'])

function nombreDeTecla(e: TeclaLike): string | null {
  const k = e.key ?? ''
  if (k === ' ' || e.code === 'Space') return 'space'
  if (SOLO_MODIFICADOR.has(k.toLowerCase())) return null
  const bajo = k.toLowerCase()
  if (bajo.length === 1 && /[a-z0-9]/.test(bajo)) return bajo
  const m = /^(?:Key([A-Z])|Digit(\d))$/.exec(e.code ?? '')
  if (m) return (m[1] ?? m[2]).toLowerCase()
  if (!k || k === 'Dead' || k === 'Unidentified') return null
  return bajo
}

/** La combinación del evento, o null si es solo un modificador o usa el modificador ajeno a la plataforma. */
export function armarCombo(e: TeclaLike, mac: boolean = esMac()): Combo | null {
  const tecla = nombreDeTecla(e)
  if (!tecla) return null
  const modPropio = mac ? !!e.metaKey : !!e.ctrlKey
  const modAjeno = mac ? !!e.ctrlKey : !!e.metaKey
  if (modAjeno) return null
  return [modPropio && 'mod', e.altKey && 'alt', e.shiftKey && 'shift', tecla].filter(Boolean).join('+')
}

export function coincide(e: TeclaLike, combo: Combo, mac: boolean = esMac()): boolean {
  const c = armarCombo(e, mac)
  if (c === combo) return true
  // Una tecla sola (como M) se dispara aunque esté el Shift o las mayúsculas.
  return !!c && !combo.includes('+') && c === `shift+${combo}`
}

/** Como `coincide`, pero Ctrl y ⌘ valen igual (para atajos que aceptaban los dos). */
export function coincideCtrlOCmd(e: TeclaLike, combo: Combo): boolean {
  return coincide(e, combo, false) || coincide(e, combo, true)
}

const NOMBRES: Record<string, string> = { space: 'Espacio', enter: 'Enter', tab: 'Tab' }

export function partesCombo(combo: Combo, mac: boolean = esMac()): string[] {
  return combo.split('+').map((p) => {
    if (p === 'mod') return mac ? '⌘' : 'Ctrl'
    if (p === 'alt') return mac ? '⌥' : 'Alt'
    if (p === 'shift') return 'Shift'
    return NOMBRES[p] ?? p.toUpperCase()
  })
}

export function etiquetaCombo(combo: Combo, mac: boolean = esMac()): string {
  return partesCombo(combo, mac).join(mac ? '' : ' ')
}

const RESERVADAS: Record<string, string> = {
  'mod+t': 'abrir una pestaña',
  'mod+shift+t': 'reabrir la última pestaña cerrada',
  'mod+w': 'cerrar la pestaña',
  'mod+shift+w': 'cerrar la ventana',
  'mod+n': 'abrir una ventana',
  'mod+shift+n': 'abrir una ventana privada',
  'mod+l': 'ir a la barra de direcciones',
  'mod+r': 'recargar la página',
  'mod+shift+r': 'recargar la página',
  f5: 'recargar la página',
  'mod+tab': 'cambiar de pestaña',
  'mod+shift+tab': 'cambiar de pestaña',
  'alt+f4': 'cerrar la ventana',
  'mod+p': 'imprimir',
  'mod+s': 'guardar la página',
  'mod+q': 'cerrar el navegador',
  'mod+f': 'buscar en la página',
  'mod+d': 'guardar en marcadores',
  'mod+h': 'abrir el historial',
}

/** Texto de error en lenguaje simple, o null si la combinación sirve para ese atajo. */
export function validarCombo(id: string, combo: Combo, efectivos: Record<string, Combo>, mac: boolean = esMac()): string | null {
  const propio = EDITABLES.find((a) => a.id === id)
  if (!propio) return 'Ese atajo no se puede cambiar'
  const reservada = RESERVADAS[combo]
  if (reservada) return `El navegador usa ${partesCombo(combo, mac).join('+')} para ${reservada}`
  const partes = combo.split('+')
  const tecla = partes[partes.length - 1]
  const mods = partes.slice(0, -1)
  if (!mods.length && propio.sinModificador && (/^[1-6]$/.test(tecla) || ['enter', 'tab', 'space'].includes(tecla)))
    return 'Esa tecla ya tiene otro uso en Te pregunta'
  if (!mods.length && !propio.sinModificador) return `Necesita ${mac ? '⌘' : 'Ctrl'}, Alt o Shift`
  if (mods.length === 1 && mods[0] === 'shift' && tecla.length === 1 && !propio.sinModificador)
    return 'Con Shift solo no alcanza: sumale Ctrl o Alt'
  for (const otro of EDITABLES) {
    if (otro.id === id) continue
    if ((efectivos[otro.id] ?? otro.original) !== combo) continue
    if (otro.ambito === 'global' || propio.ambito === 'global' || otro.ambito === propio.ambito) return `Ya la usa «${otro.que}»`
  }
  return null
}
