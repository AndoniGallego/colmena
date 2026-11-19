import { ApiError, type Board, type Tab, type Terminal, type TerminalPreview, type Workspace } from '../api/types'

export interface TerminalRef {
  ws: Workspace
  tab: Tab
  terminal: Terminal
}

export function findTerminal(board: Board | null, paneId: string | null): TerminalRef | null {
  if (!paneId || !board) return null
  for (const ws of board.workspaces)
    for (const tab of ws.tabs) {
      const terminal = (tab.terminales ?? []).find((t) => t.pane_id === paneId)
      if (terminal) return { ws, tab, terminal }
    }
  return null
}

export const ESTADO_LABEL: Record<string, string> = {
  prompt: 'en el prompt',
  corriendo: 'corriendo',
  desconocido: 'sin datos',
}

export function terminalTitle(t: Terminal): string {
  return t.titulo || t.proceso || 'Terminal'
}

const RULES: Array<[RegExp, string]> = [
  [/escritura apagada/, 'La escritura de terminales está apagada'],
  [/sesión de agente/, 'Es una sesión de Claude: no se cierra desde acá'],
  [/panel del orquestador/, 'Es el panel de Colmena: no se cierra desde acá'],
  [/ubicar su pestaña/, 'La terminal cambió. Revisala de nuevo'],
  [/ya se hizo/, 'Eso ya se hizo'],
  [/workspace protegido/, 'Ese workspace está protegido'],
  [/la terminal cambió/, 'La terminal cambió. Revisala de nuevo'],
  [/se movió o cambió de carpeta/, 'La terminal se movió o cambió de carpeta desde el pedido. Revisala antes de cerrarla'],
  [/quedó sola en su pestaña/, 'La terminal quedó sola en su pestaña. Revisala de nuevo'],
  [/la terminal ya no está/, 'La terminal ya no está'],
  [/programa corriendo/, 'Hay un programa corriendo: frenalo primero'],
  [/la línea cambió|confirmación venció/, 'La línea cambió. Preparala de nuevo'],
]

/** Frases fijas del servidor traducidas a un mensaje corto; lo que no se reconoce no se muestra tal cual. */
export function terminalError(e: unknown): string {
  if (!(e instanceof ApiError)) return 'No pude conectar con el servidor'
  // Un pedido descartado lo dice aunque venga con 502/500: el motivo importa más que el código.
  if (/otra terminal/.test(e.detail)) return 'Ahora es otra terminal: descarté el pedido'
  if (/descarté el pedido/.test(e.detail)) return 'No pude cerrar la terminal: descarté el pedido'
  if (e.status === 401 && /abrí la escritura/.test(e.detail)) return 'Se cerró la escritura. Abrila de nuevo con el PIN'
  if (e.status === 429) return e.retryAfter ? `Demasiadas acciones seguidas. Probá en ${e.retryAfter} s` : 'Demasiadas acciones seguidas'
  if (e.status === 502) return 'Las terminales no respondieron'
  if (e.status === 401) return 'Tu sesión venció'
  for (const [re, text] of RULES) if (re.test(e.detail)) return text
  return e.status >= 500 ? 'Algo falló en el servidor' : 'No se pudo hacer'
}

/** Aviso de la hoja cuando cerrar se lleva más que la terminal. */
export function notaCierre(p: Pick<TerminalPreview, 'cierra' | 'tab' | 'workspace'>): string {
  if (p.cierra === 'pestana') return `Es la única terminal de su pestaña: se cierra la pestaña${p.tab ? ` «${p.tab}»` : ''} entera.`
  if (p.cierra === 'espacio') return `Es la única terminal del workspace: se cierra el workspace${p.workspace ? ` «${p.workspace}»` : ''} entero.`
  return ''
}

export type AccionKind = 'ctrl-c' | 'repetir' | 'comando' | 'cerrar'

export const MAX_COMANDO = 500
// Igual que el servidor: control, formato (bidi, ancho cero), sustitutos sueltos, uso privado, sin asignar,
// separadores de línea/párrafo, espacios que no son el común y rellenos que no se ven.
const PROHIBIDO = '[\\p{Cc}\\p{Cf}\\p{Cs}\\p{Co}\\p{Cn}\\p{Zl}\\p{Zp}\\u115F\\u1160\\u3164\\uFFA0\\u2800]|(?! )\\p{Zs}'
const INVISIBLE = new RegExp(PROHIBIDO, 'u')
const INVISIBLE_ALL = new RegExp(PROHIBIDO, 'gu')

/** Réplica de la validación del servidor para avisar antes de abrir el PIN; el servidor decide. */
export function validarComando(raw: string): string | null {
  const text = raw.normalize('NFC')
  if (!text) return 'Escribí un comando'
  if (text.length > MAX_COMANDO) return `Máximo ${MAX_COMANDO} caracteres`
  if (INVISIBLE.test(text)) return 'El comando tiene caracteres no permitidos (saltos de línea, tabulaciones, invisibles o espacios raros)'
  if (text !== text.trim() || !text.trim()) return 'Sin espacios al principio ni al final'
  if (text.startsWith('-')) return 'No puede empezar con -'
  return null
}

/** Los invisibles se muestran como ⟨U+XXXX⟩ para que lo que se ve sea lo que va. */
export function verInvisibles(text: string): string {
  return text.replace(INVISIBLE_ALL, (c) => `⟨U+${c.codePointAt(0)!.toString(16).toUpperCase().padStart(4, '0')}⟩`)
}

export const HISTORIAL_MAX = 30
const SECRETISH = /(password|passwd|pwd\s*[=:]|token|secret|api[_-]?key|authorization|bearer)|:\/\/[^/\s:@]+:[^@\s]+@|\bAKIA[0-9A-Z]{16}|\b(ghp_|github_pat_|glpat-|sk-)/i

/** Historial local: lo más nuevo primero, sin repetidos y sin comandos que parezcan llevar un secreto. */
export function addHistorial(list: string[], cmd: string): string[] {
  if (SECRETISH.test(cmd)) return list
  return [cmd, ...list.filter((c) => c !== cmd)].slice(0, HISTORIAL_MAX)
}
