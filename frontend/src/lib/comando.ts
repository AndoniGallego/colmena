import { reactive } from 'vue'
import { clipPalabras } from './estado'

export interface Comando {
  comando: string
  motivo: string
  /** Lo que pidió la sesión; no se muestra: tiene que coincidir con el cwd real o la tarjeta es inválida. */
  carpeta?: string
  /** Por qué no se puede correr; el servidor lo rechazaría igual. */
  error?: string
}

export const COMANDO_LIMITES = { comando: 500, motivo: 200, carpeta: 500 } as const

// Lo mismo que terminales_acciones.validar_comando: lo que se confirma tiene que ser lo que se lee.
const PROHIBIDAS = /[\p{Cc}\p{Cf}\p{Cs}\p{Co}\p{Cn}\p{Zl}\p{Zp}\p{Default_Ignorable_Code_Point}ᅟᅠㅤﾠ⠀]/u
const ESPACIO = /\p{Zs}/u

export function validarComando(raw: string): string | null {
  const text = raw.normalize('NFC')
  if (/[\n\r]/.test(text)) return 'tiene más de una línea'
  if (text.length < 1 || text.length > COMANDO_LIMITES.comando) return `tiene que tener entre 1 y ${COMANDO_LIMITES.comando} caracteres`
  for (const c of text) {
    if (PROHIBIDAS.test(c) || (c !== ' ' && ESPACIO.test(c))) return 'tiene caracteres invisibles o de control'
  }
  if (text !== text.trim()) return 'no puede empezar ni terminar con espacios'
  if (text.startsWith('-')) return 'no puede empezar con -'
  // Con `\` al final el Enter agrega una línea en vez de mandar el comando.
  if (text.endsWith('\\')) return 'no puede terminar con \\'
  return null
}

/** Todo bloque con un `comando` de texto es tarjeta (aunque sea inválido): así el índice coincide con el del servidor. */
export function toComando(value: unknown): Comando | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const o = value as Record<string, unknown>
  if (typeof o.comando !== 'string' || !o.comando) return null
  const out: Comando = {
    comando: o.comando.normalize('NFC'),
    motivo: typeof o.motivo === 'string' ? clipPalabras(o.motivo, COMANDO_LIMITES.motivo) : '',
  }
  if (typeof o.carpeta === 'string') {
    const c = o.carpeta.trim()
    if (c) out.carpeta = c.slice(0, COMANDO_LIMITES.carpeta)
  }
  const error = validarComando(out.comando)
  if (error) out.error = error
  return out
}

export const CARPETA_DISTINTA = 'La carpeta pedida no es donde corre la sesión'

function normalizarRuta(p: string): string {
  const partes: string[] = []
  for (const x of p.split('/')) {
    if (!x || x === '.') continue
    if (x === '..') partes.pop()
    else partes.push(x)
  }
  return '/' + partes.join('/')
}

/** La carpeta pedida no sirve si es relativa o si no es el cwd real (cuando se conoce); el servidor igual lo exige. */
export function carpetaDistinta(carpeta: string | undefined, cwd: string | undefined): boolean {
  if (!carpeta) return false
  if (!carpeta.startsWith('/')) return true
  return !!cwd && normalizarRuta(carpeta) !== normalizarRuta(cwd)
}

/** El comando en tramos: los caracteres fuera de ASCII imprimible van aparte para resaltarlos. */
export function tramosComando(cmd: string): { texto: string; raro: boolean }[] {
  const out: { texto: string; raro: boolean }[] = []
  for (const c of cmd) {
    const raro = !/^[\x20-\x7e]$/.test(c)
    const last = out.at(-1)
    if (last && last.raro === raro) last.texto += c
    else out.push({ texto: c, raro })
  }
  return out
}

export type EstadoComando =
  | { fase: 'listo' }
  | { fase: 'corriendo' }
  | { fase: 'corrido'; ya?: boolean }
  | { fase: 'descartado' }
  | { fase: 'error'; detalle: string }

// Por tarjeta (sesión, mensaje, índice): sobrevive a que la conversación se vuelva a dibujar.
const estados = reactive(new Map<string, EstadoComando>())

export const claveComando = (sid: string, mid: string, indice: number) => `${sid}\u0000${mid}\u0000${indice}`
export const estadoComando = (clave: string): EstadoComando => estados.get(clave) ?? { fase: 'listo' }
export function ponerEstadoComando(clave: string, e: EstadoComando) {
  estados.set(clave, e)
}
export function olvidarComandos() {
  estados.clear()
}
