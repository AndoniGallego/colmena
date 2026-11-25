import { coincide } from './teclas'

export const MAX_SECONDS = 120
export const WARN_AT = 110
export const MIN_SECONDS = 0.5
export const MIN_BYTES = 1200

const MIME_ORDER = ['audio/webm;codecs=opus', 'audio/mp4', 'audio/webm', 'audio/ogg;codecs=opus']

/** Chrome/Edge graban webm/opus; iOS solo mp4. Se pregunta en runtime y, si nada coincide, elige el navegador. */
export function pickMimeType(isSupported: (type: string) => boolean): string {
  for (const type of MIME_ORDER) {
    try {
      if (isSupported(type)) return type
    } catch {
      /* isTypeSupported puede tirar con tipos raros */
    }
  }
  return ''
}

export function extFor(mime: string): string {
  const base = mime.split(';')[0].trim().toLowerCase()
  if (base.includes('mp4') || base.includes('m4a') || base.includes('aac')) return 'm4a'
  if (base.includes('ogg')) return 'ogg'
  if (base.includes('wav')) return 'wav'
  return 'webm'
}

/** Mete `insert` en la selección con un espacio de cortesía a cada lado; devuelve el cursor al final de lo insertado. */
export function insertAtCursor(text: string, start: number | null | undefined, end: number | null | undefined, insert: string) {
  const s = Math.max(0, Math.min(start ?? text.length, text.length))
  const e = Math.max(s, Math.min(end ?? s, text.length))
  const piece = insert.trim()
  if (!piece) return { text, cursor: s }
  const before = text.slice(0, s)
  const after = text.slice(e)
  const lead = before && !/\s$/.test(before) ? ' ' : ''
  const tail = after && !/^\s/.test(after) ? ' ' : ''
  const head = before + lead + piece
  return { text: head + tail + after, cursor: head.length }
}

export function formatClock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

export type VozErrorKind =
  | 'permiso'
  | 'sin-microfono'
  | 'mic-ocupado'
  | 'no-soportado'
  | 'silencio'
  | 'corto'
  | 'ocupada'
  | 'larga'
  | 'modelo'
  | 'deshabilitada'
  | 'tiempo'
  | 'red'
  | 'server'

export interface VozError {
  kind: VozErrorKind
  title: string
  hint: string
}

export function isIOS(ua = '', platform = '', touchPoints = 0): boolean {
  return /iPhone|iPad|iPod/.test(ua) || (platform === 'MacIntel' && touchPoints > 1)
}

export function permissionHint(ios: boolean): string {
  return ios
    ? 'En el iPhone: Ajustes › Apps › Safari › Micrófono, y permitilo para este sitio. Después tocá el micrófono otra vez.'
    : 'Tocá el candado junto a la dirección, permití el micrófono para este sitio y volvé a intentar.'
}

export function vozError(kind: VozErrorKind, opts: { ios?: boolean; detail?: string } = {}): VozError {
  const copy: Record<VozErrorKind, [string, string]> = {
    permiso: ['No tengo permiso para usar el micrófono.', permissionHint(!!opts.ios)],
    'sin-microfono': ['No encontré ningún micrófono.', 'Conectá uno o revisá que el sistema lo detecte.'],
    'mic-ocupado': ['El micrófono está en uso por otra app.', 'Cerrala o esperá a que lo suelte y probá de nuevo.'],
    'no-soportado': ['Este navegador no puede grabar audio.', 'Probá con Chrome, Edge o Safari actualizados.'],
    silencio: ['No se escuchó nada.', 'Acercate al micrófono y probá de nuevo.'],
    corto: ['La grabación fue muy corta.', 'Hablá al menos un segundo antes de terminar.'],
    ocupada: ['Todavía estoy transcribiendo otro audio.', 'Esperá unos segundos y probá de nuevo.'],
    larga: ['El audio es demasiado largo o pesado.', 'El máximo es de 2 minutos.'],
    modelo: ['El modelo de voz no está instalado en la notebook.', 'Hay que descargarlo una vez: uv run orquestador descargar-modelo.'],
    deshabilitada: ['El dictado por voz está desactivado.', 'Se prende con voz_habilitada en config.toml.'],
    tiempo: ['La transcripción tardó demasiado.', 'Probá con un audio más corto.'],
    red: ['Se cortó la conexión con el servidor.', 'El audio no se perdió en ningún lado: grabalo de nuevo.'],
    server: ['No pude transcribir el audio.', 'Probá de nuevo; si sigue fallando, revisá el servidor.'],
  }
  const [title, hint] = copy[kind]
  return { kind, title, hint }
}

export function kindFromMediaError(name: string): VozErrorKind {
  if (name === 'NotAllowedError' || name === 'SecurityError' || name === 'PermissionDeniedError') return 'permiso'
  if (name === 'NotFoundError' || name === 'OverconstrainedError' || name === 'DevicesNotFoundError') return 'sin-microfono'
  if (name === 'NotReadableError' || name === 'AbortError' || name === 'TrackStartError') return 'mic-ocupado'
  return 'server'
}

export function kindFromStatus(status: number): VozErrorKind {
  if (status === 0) return 'red'
  if (status === 409) return 'ocupada'
  if (status === 404) return 'deshabilitada'
  if (status === 413) return 'larga'
  if (status === 503) return 'modelo'
  if (status === 504 || status === 408) return 'tiempo'
  return 'server'
}

type KeyLike = Pick<KeyboardEvent, 'code' | 'ctrlKey' | 'shiftKey' | 'altKey' | 'metaKey'> & { key?: string }

/** Por defecto Ctrl+Shift+Espacio: Chrome/Edge ya usan Ctrl+Shift+M (perfil), Alt+Espacio (menú de la ventana) y Alt+Shift (idioma de Windows). */
export const SHORTCUT_COMBO = 'mod+shift+space'
export function isVozShortcut(e: KeyLike, combo: string = SHORTCUT_COMBO): boolean {
  return coincide({ ...e, key: e.key ?? '' }, combo)
}
