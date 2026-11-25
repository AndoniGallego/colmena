import { postJson, type Invoke } from './nudoPuente'

export type NivelRegistro = 'info' | 'aviso' | 'error'
type Post = (url: string, body: unknown) => Promise<unknown>

export const INTERVALO_MS = 30_000
export const TRAS_ERROR_MS = 2_000
export const LOTES_POR_CICLO = 5

const URL_REGISTRO = '/api/registro/app'
const MAX_MENSAJE = 300

function invokeDe(w: Window): Invoke | null {
  const invoke = w.__TAURI__?.core?.invoke
  return typeof invoke === 'function' ? invoke : null
}

/** No hace nada fuera del programa y nunca lanza: anotar no puede romper a quien anota. */
export function anotarNotch(nivel: NivelRegistro, mensaje: string, w: Window = window): void {
  try {
    const invoke = invokeDe(w)
    if (!invoke) return
    invoke('registro_anotar', { nivel, mensaje }).catch(() => undefined)
  } catch {
    // sin rastro: el registro no se registra a sí mismo
  }
}

const TOKEN_RE = /^[a-z0-9_]{1,40}$/
const token = (s: string) => (TOKEN_RE.test(s) ? s : 'otro')

/** Evento de telemetría del notch: solo tokens, nunca texto. Rust fija el origen en "notch". */
function eventoNotch(evento: string, ok: boolean, codigo: string | undefined, w: Window): void {
  try {
    const invoke = invokeDe(w)
    if (!invoke) return
    invoke('registro_evento', { origen: 'notch', evento: token(evento), ok, ...(codigo ? { codigo } : {}) }).catch(() => undefined)
  } catch {
    // sin rastro: la telemetría no puede romper a quien la emite
  }
}

/** Un invoke que falló: el código es `invoke_<comando>` o `otro` si no entra en 40 caracteres. */
export function anotarInvokeFallido(comando: string, w: Window = window): void {
  eventoNotch('error', false, token(`invoke_${comando}`), w)
}

/** Avisa conectado/desconectado solo cuando cambia; el estado inicial es desconocido, así que la primera noticia siempre se emite. */
export function crearReporteConexion(w: Window = window): (conectado: boolean) => void {
  let ultimo: boolean | null = null
  return (conectado) => {
    if (conectado === ultimo) return
    ultimo = conectado
    if (conectado) eventoNotch('conectado', true, undefined, w)
    else eventoNotch('desconectado', false, 'red', w)
  }
}

function nombreBase(url: string): string {
  return url.split('#')[0].split('?')[0].split('/').pop() ?? ''
}

function textoDeError(e: Error): string {
  // El message de un SyntaxError de JSON.parse trae un fragmento del texto parseado.
  return e.name === 'SyntaxError' ? e.name : `${e.name}: ${e.message}`
}

function textoDeEvento(e: ErrorEvent): string {
  let base: string
  if (e.error instanceof Error) base = textoDeError(e.error)
  else if (e.error !== undefined && e.error !== null) base = `rechazo: ${typeof e.error}`
  else base = /SyntaxError/.test(e.message ?? '') ? 'SyntaxError' : (e.message ?? '')
  const archivo = nombreBase(e.filename ?? '')
  return archivo ? `${base} (${archivo}:${e.lineno})` : base
}

/** Solo códigos de error y el nombre del archivo; nunca contenido de usuario. */
export function mensajeDeError(e: unknown): string {
  let texto: string
  if (e instanceof Error) texto = textoDeError(e)
  else if (typeof ErrorEvent !== 'undefined' && e instanceof ErrorEvent) texto = textoDeEvento(e)
  else texto = `rechazo: ${typeof e}`
  return texto.slice(0, MAX_MENSAJE)
}

type Lote = { lote: number; lineas?: unknown[]; eventos?: unknown[] }

export async function enviarPendientes(
  deps: { invoke: Invoke; post: Post },
  maxLotes: number = LOTES_POR_CICLO,
): Promise<'vacio' | 'enviado' | 'fallo'> {
  let enviados = 0
  try {
    while (enviados < maxLotes) {
      const pendiente = (await deps.invoke('registro_pendiente')) as Lote | null
      if (!pendiente) break
      const lineas = pendiente.lineas ?? []
      const eventos = pendiente.eventos ?? []
      await deps.post(URL_REGISTRO, {
        ...(lineas.length > 0 ? { lineas } : {}),
        ...(eventos.length > 0 ? { eventos } : {}),
      })
      await deps.invoke('registro_enviado', { lote: pendiente.lote })
      enviados++
    }
  } catch {
    return 'fallo'
  }
  return enviados > 0 ? 'enviado' : 'vacio'
}

export function iniciarRegistroNotch(opts: { w?: Window; post?: Post } = {}): () => void {
  const w = opts.w ?? window
  const invoke = invokeDe(w)
  if (!invoke) return () => {}
  const post = opts.post ?? postJson

  let enCurso = false
  let parado = false
  let pendienteTimer: ReturnType<typeof setTimeout> | undefined

  const ciclo = async () => {
    if (enCurso || parado) return
    enCurso = true
    try {
      await enviarPendientes({ invoke, post })
    } finally {
      enCurso = false
    }
  }

  const programar = () => {
    if (parado) return
    clearTimeout(pendienteTimer)
    pendienteTimer = setTimeout(() => void ciclo(), TRAS_ERROR_MS)
  }

  const alError = (e: Event) => {
    anotarNotch('error', mensajeDeError(e), w)
    eventoNotch('error', false, 'onerror', w)
    programar()
  }
  const alRechazo = (e: Event) => {
    anotarNotch('error', mensajeDeError((e as PromiseRejectionEvent).reason), w)
    eventoNotch('error', false, 'promesa', w)
    programar()
  }

  w.addEventListener('error', alError)
  w.addEventListener('unhandledrejection', alRechazo)
  const intervalo = setInterval(() => void ciclo(), INTERVALO_MS)
  const listen = w.__TAURI__?.event?.listen
  if (typeof listen === 'function') {
    try {
      Promise.resolve(listen('registro-hay', () => programar())).catch(() => undefined)
    } catch {
      // sin el evento queda el ciclo de 30 s
    }
  }

  return () => {
    parado = true
    clearInterval(intervalo)
    clearTimeout(pendienteTimer)
    w.removeEventListener('error', alError)
    w.removeEventListener('unhandledrejection', alRechazo)
  }
}
