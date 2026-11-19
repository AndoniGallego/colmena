export function urlVivo(paneId: string, loc: { protocol: string; host: string }): string {
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${loc.host}/api/terminal/${encodeURIComponent(paneId)}/vivo`
}

export type MensajeVivo =
  | { tipo: 'foto'; columnas: number; filas: number; texto: string }
  | { tipo: 'salida'; texto: string }
  | { tipo: 'termino'; codigo: number | null }
  | { tipo: 'cerrada' }
  | { tipo: 'caido' }
  | { tipo: 'desfasado' }
  | { tipo: 'error'; codigo: 'apagado' | 'no_es_propia' | 'no_existe' | 'cupo' | 'sesion'; mensaje: string }
  | { tipo: 'error_escritura'; codigo: 'ventana' | 'apagado' | 'caido'; mensaje: string }

const ERR_FINAL = new Set(['apagado', 'no_es_propia', 'no_existe'])
const ERR_COD = new Set(['apagado', 'no_es_propia', 'no_existe', 'cupo', 'sesion'])

function intRango(v: unknown, min: number, max: number): number | null {
  if (typeof v !== 'number' || !Number.isInteger(v) || v < min || v > max) return null
  return v
}

function str(v: unknown): string | null {
  return typeof v === 'string' ? v : null
}

export function parseMensajeVivo(data: unknown): MensajeVivo | null {
  if (!data || typeof data !== 'object') return null
  const o = data as Record<string, unknown>
  const tipo = o.tipo
  if (tipo === 'foto') {
    const columnas = intRango(o.columnas, 1, 1000)
    const filas = intRango(o.filas, 1, 1000)
    const texto = str(o.texto)
    if (columnas === null || filas === null || texto === null) return null
    return { tipo: 'foto', columnas, filas, texto }
  }
  if (tipo === 'salida') {
    const texto = str(o.texto)
    if (texto === null) return null
    return { tipo: 'salida', texto }
  }
  if (tipo === 'termino') {
    if (o.codigo === null || o.codigo === undefined) return { tipo: 'termino', codigo: null }
    if (typeof o.codigo !== 'number' || !Number.isInteger(o.codigo)) return null
    return { tipo: 'termino', codigo: o.codigo }
  }
  if (tipo === 'cerrada' || tipo === 'caido' || tipo === 'desfasado') return { tipo }
  if (tipo === 'error') {
    const codigo = o.codigo
    const mensaje = str(o.mensaje)
    if (!ERR_COD.has(codigo as string) || mensaje === null) return null
    return {
      tipo: 'error',
      codigo: codigo as 'apagado' | 'no_es_propia' | 'no_existe' | 'cupo' | 'sesion',
      mensaje,
    }
  }
  if (tipo === 'error_escritura') {
    const codigo = o.codigo
    const mensaje = str(o.mensaje)
    if (codigo !== 'ventana' && codigo !== 'apagado' && codigo !== 'caido') return null
    if (mensaje === null) return null
    return { tipo: 'error_escritura', codigo, mensaje }
  }
  return null
}

export type EstadoVivo = 'conectando' | 'en_vivo' | 'reconectando' | 'terminada' | 'cerrada' | 'caido' | 'error'

export function textoEstado(estado: EstadoVivo): string {
  switch (estado) {
    case 'conectando':
      return 'Conectando…'
    case 'en_vivo':
      return 'En vivo'
    case 'reconectando':
      return 'Reconectando…'
    case 'terminada':
      return 'Terminada'
    case 'cerrada':
      return 'Cerrada'
    case 'caido':
      return 'Sin respuesta'
    case 'error':
      return 'Error'
  }
}

export const MSG_SESION_VENCIDA = 'Tu sesión de Colmena venció. Volvé a entrar.'
export const MSG_NO_CONECTE =
  'No pude conectarme. Puede que tu sesión haya vencido: recargá la app.'

export interface FotoVivo {
  columnas: number
  filas: number
  texto: string
}

export interface WebSocketLike {
  close(): void
  send?(data: string): void
  addEventListener?(type: string, listener: (...args: unknown[]) => void): void
  removeEventListener?(type: string, listener: (...args: unknown[]) => void): void
  onopen: ((ev: Event) => void) | null
  onmessage: ((ev: { data: string }) => void) | null
  onclose: ((ev: { code: number }) => void) | null
  onerror: ((ev: Event) => void) | null
  readyState?: number
}

export interface ConexionVivoDeps {
  crearSocket: (url: string) => WebSocketLike
  setTimeout: (fn: () => void, ms: number) => number
  clearTimeout: (id: number) => void
}

export interface ConexionVivoOpts {
  paneId: string
  loc: { protocol: string; host: string }
  deps: ConexionVivoDeps
  onFoto: (f: FotoVivo) => void
  onSalida: (texto: string) => void
  onEstado: (estado: EstadoVivo, mensaje?: string, extra?: { codigo?: number | null; reintentar?: boolean }) => void
  onErrorEscritura?: (codigo: 'ventana' | 'apagado' | 'caido', mensaje: string) => void
}

const BACKOFF_MS = [500, 1000, 2000, 4000, 8000, 15000]

function backoffOrdinario(i: number): number {
  return BACKOFF_MS[Math.min(i, BACKOFF_MS.length - 1)]!
}

export class ConexionVivo {
  private url: string
  private deps: ConexionVivoDeps
  private onFoto: (f: FotoVivo) => void
  private onSalida: (texto: string) => void
  private onEstado: ConexionVivoOpts['onEstado']
  private onErrorEscritura: ConexionVivoOpts['onErrorEscritura']

  private socket: WebSocketLike | null = null
  private timer: number | null = null
  private final = false
  private cerrado = false
  private recibioMensaje = false
  private fallosSinMensaje = 0
  private backoff = 0
  private caidoBackoff = 0
  private modoCaido = false
  private reconectarYa = false
  private tuvoFoto = false
  private mensajeError: string | undefined
  private puedeReintentar = false
  constructor(opts: ConexionVivoOpts) {
    this.url = urlVivo(opts.paneId, opts.loc)
    this.deps = opts.deps
    this.onFoto = opts.onFoto
    this.onSalida = opts.onSalida
    this.onEstado = opts.onEstado
    this.onErrorEscritura = opts.onErrorEscritura
  }

  enviar(payload: object): void {
    const s = this.socket
    if (!s || s.readyState !== 1) return
    try {
      s.send?.(JSON.stringify(payload))
    } catch {
      /* noop */
    }
  }

  abrir(): void {
    if (this.cerrado || this.final) return
    this.conectar(false)
  }

  cerrar(): void {
    this.cerrado = true
    this.final = true
    this.limpiarTimer()
    this.cortarSocket()
  }

  reintentar(): void {
    if (this.cerrado) return
    this.final = false
    this.fallosSinMensaje = 0
    this.backoff = 0
    this.caidoBackoff = 0
    this.modoCaido = false
    this.mensajeError = undefined
    this.puedeReintentar = false
    this.limpiarTimer()
    this.cortarSocket()
    this.conectar(false)
  }

  /** Reconexión inmediata (red online o pestaña visible). */
  despertar(): void {
    if (this.cerrado || this.final || this.socket) return
    if (this.timer !== null) {
      this.limpiarTimer()
      this.conectar(this.tuvoFoto)
    }
  }

  private limpiarTimer(): void {
    if (this.timer !== null) {
      this.deps.clearTimeout(this.timer)
      this.timer = null
    }
  }

  private cortarSocket(): void {
    const s = this.socket
    if (!s) return
    s.onopen = null
    s.onmessage = null
    s.onclose = null
    s.onerror = null
    try {
      s.close()
    } catch {
      /* noop */
    }
    this.socket = null
  }

  private conectar(reconectando: boolean): void {
    if (this.cerrado || this.final) return
    this.limpiarTimer()
    this.cortarSocket()
    this.reconectarYa = false
    this.onEstado(reconectando || this.tuvoFoto ? 'reconectando' : 'conectando')

    const ws = this.deps.crearSocket(this.url)
    this.socket = ws

    ws.onopen = () => {
      if (this.cerrado || this.final) return
    }

    ws.onmessage = (ev) => {
      if (this.cerrado) return
      let raw: unknown
      try {
        raw = JSON.parse(ev.data)
      } catch {
        return
      }
      const msg = parseMensajeVivo(raw)
      if (!msg) return
      this.recibioMensaje = true
      this.fallosSinMensaje = 0
      this.handle(msg)
    }

    ws.onclose = (ev) => {
      if (this.cerrado) return
      this.socket = null
      this.onClose(ev.code)
    }

    ws.onerror = () => {
      /* el cierre llega por onclose */
    }
  }

  private handle(msg: MensajeVivo): void {
    switch (msg.tipo) {
      case 'foto':
        this.tuvoFoto = true
        this.backoff = 0
        this.caidoBackoff = 0
        this.modoCaido = false
        this.onFoto({ columnas: msg.columnas, filas: msg.filas, texto: msg.texto })
        this.onEstado('en_vivo')
        break
      case 'salida':
        this.onSalida(msg.texto)
        break
      case 'termino':
        this.final = true
        this.onEstado('terminada', undefined, { codigo: msg.codigo ?? null })
        this.cortarSocket()
        break
      case 'cerrada':
        this.final = true
        this.onEstado('cerrada')
        this.cortarSocket()
        break
      case 'caido':
        this.modoCaido = true
        this.onEstado('caido')
        break
      case 'desfasado':
        this.reconectarYa = true
        break
      case 'error':
        this.mensajeError = msg.codigo === 'sesion' ? MSG_SESION_VENCIDA : msg.mensaje
        this.puedeReintentar = msg.codigo === 'cupo'
        if (ERR_FINAL.has(msg.codigo) || msg.codigo === 'cupo' || msg.codigo === 'sesion') {
          this.final = true
          this.onEstado('error', this.mensajeError, { reintentar: this.puedeReintentar })
        }
        break
      case 'error_escritura':
        this.onErrorEscritura?.(msg.codigo, msg.mensaje)
        break
    }
  }

  private onClose(code: number): void {
    if (this.cerrado || this.final) return

    if (!this.recibioMensaje) {
      this.fallosSinMensaje++
      if (this.fallosSinMensaje >= 2) {
        this.final = true
        this.puedeReintentar = true
        this.onEstado('error', MSG_NO_CONECTE, { reintentar: true })
        return
      }
      this.programar(false, 300)
      return
    }

    if (this.modoCaido) {
      this.modoCaido = false
      const ms = backoffOrdinario(this.caidoBackoff++)
      this.onEstado('caido')
      this.programar(true, ms)
      return
    }

    if (this.reconectarYa) {
      this.reconectarYa = false
      this.programar(true, 0)
      return
    }

    if (this.tuvoFoto) {
      const ms = backoffOrdinario(this.backoff++)
      this.onEstado('reconectando')
      this.programar(true, ms)
    }
  }

  private programar(reconectando: boolean, ms: number): void {
    if (this.cerrado || this.final) return
    this.limpiarTimer()
    this.timer = this.deps.setTimeout(() => {
      this.timer = null
      this.recibioMensaje = false
      this.conectar(reconectando)
    }, ms)
  }
}
