export type EstadoLector = 'escuchando' | 'sin_subtitulos' | 'pausado' | 'apagado'

const ESTADOS_LECTOR: readonly string[] = ['escuchando', 'sin_subtitulos', 'pausado', 'apagado']

/** El back acepta de 1 a 2000 caracteres por POST de texto. */
export const TEXTO_POST_MAX = 2000
const COLA_MAX = 20_000
const MARCA = '[…] '

/** Texto del lector que espera salir: acotado, con lo más viejo descartado primero. */
export class ColaTexto {
  private buf = ''

  constructor(private readonly max = COLA_MAX) {}

  private acotar() {
    if (this.buf.length <= this.max) return
    const sin = this.buf.startsWith(MARCA) ? this.buf.slice(MARCA.length) : this.buf
    this.buf = MARCA + sin.slice(sin.length - Math.max(0, this.max - MARCA.length))
  }

  agregar(t: string): void {
    const s = t.trim()
    if (!s) return
    this.buf = this.buf ? `${this.buf} ${s}` : s
    this.acotar()
  }

  /** Hasta 2000 caracteres del frente, cortando en un espacio si hay resto. Null si no hay nada que mandar. */
  tomar(): string | null {
    if (!this.buf.trim()) {
      this.buf = ''
      return null
    }
    let corte = this.buf.length
    if (corte > TEXTO_POST_MAX) {
      corte = TEXTO_POST_MAX
      const espacio = this.buf.lastIndexOf(' ', TEXTO_POST_MAX)
      if (espacio > TEXTO_POST_MAX / 2) corte = espacio
    }
    const t = this.buf.slice(0, corte).trim()
    this.buf = this.buf.slice(corte).trim()
    return t || null
  }

  /** Un envío que falló vuelve al frente. */
  devolver(t: string): void {
    this.buf = this.buf ? `${t} ${this.buf}` : t
    this.acotar()
  }

  descartar(): void {
    this.buf = ''
  }

  get largo(): number {
    return this.buf.length
  }
}

export function normalizarLector(raw: unknown): { estado: EstadoLector; motivo?: string } | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.estado !== 'string' || !ESTADOS_LECTOR.includes(o.estado)) return null
  const estado = o.estado as EstadoLector
  return typeof o.motivo === 'string' && o.motivo ? { estado, motivo: o.motivo } : { estado }
}

export function normalizarTextoLector(raw: unknown): { texto: string; ts: number } | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.texto !== 'string') return null
  const texto = o.texto.trim()
  if (!texto || o.texto.length > TEXTO_POST_MAX) return null
  return { texto, ts: typeof o.ts === 'number' && Number.isFinite(o.ts) ? o.ts : 0 }
}

type Evento = { payload: unknown }
type Unlisten = () => void

export interface DepsLector {
  listen: (evento: string, cb: (e: Evento) => void) => Promise<Unlisten>
  invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>
  post: (url: string, body: unknown) => Promise<unknown>
  reunionId: () => string | null
  device: string
  alLector: (e: EstadoLector, motivo?: string) => void
}

export type LectorConectado = (() => void) & { vaciar(): Promise<void>; descartar(): void }

/** Escucha al lector de la app de Windows y manda su texto al back; lo que no sale queda en la cola. */
export async function conectarLector(deps: DepsLector): Promise<LectorConectado> {
  const cola = new ColaTexto()
  let enCurso: Promise<void> | null = null
  /** La cola pertenece a una reunión: si cambia, lo pendiente se tira. */
  let colaDe: string | null = null

  const paraReunion = (id: string | null): boolean => {
    if (id !== colaDe) cola.descartar()
    colaDe = id
    return id !== null
  }

  const drenar = async () => {
    for (;;) {
      const reunion = deps.reunionId()
      if (!paraReunion(reunion) || !reunion) return
      const texto = cola.tomar()
      if (texto === null) return
      try {
        await deps.post('/api/reunion/texto', { reunion, device: deps.device, texto })
      } catch {
        if (deps.reunionId() === reunion) cola.devolver(texto)
        return
      }
    }
  }

  const enviar = (): Promise<void> => {
    if (!enCurso) {
      enCurso = drenar().finally(() => {
        enCurso = null
      })
    }
    return enCurso
  }

  const desuscribir: Unlisten[] = []
  desuscribir.push(
    await deps.listen('reunion-texto', (e) => {
      const t = normalizarTextoLector(e?.payload)
      if (!t) return
      if (!paraReunion(deps.reunionId())) return
      cola.agregar(t.texto)
      void enviar()
    }),
  )
  desuscribir.push(
    await deps.listen('reunion-lector', (e) => {
      const l = normalizarLector(e?.payload)
      if (l) deps.alLector(l.estado, l.motivo)
    }),
  )

  try {
    const l = normalizarLector({ estado: await deps.invoke('reunion_estado') })
    if (l) deps.alLector(l.estado)
  } catch {
    // Sin el estado inicial el lector avisa en su próximo cambio.
  }

  const salir = (() => {
    for (const u of desuscribir) u()
  }) as LectorConectado
  salir.vaciar = async () => {
    if (enCurso) await enCurso
    await enviar()
  }
  salir.descartar = () => cola.descartar()
  return salir
}
