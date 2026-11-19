import { reactive } from 'vue'
import { postComentariosDiff } from '../api/comentariosApi'
import { ApiError } from '../api/types'
import type { ComentarioDiff } from '../lib/diffComentarios'
import { MAX_COMENTARIOS } from '../lib/diffComentarios'

const KEY = 'orq.comentariosDiff'
const YA_SE_MANDO = 'Ya se mandó'

type Fase = 'idle' | 'enviando' | 'error' | 'ok'

export const diffComentarios = reactive<{
  porSesion: Record<string, ComentarioDiff[]>
  estado: Record<string, { fase: Fase; error: string }>
}>({ porSesion: {}, estado: {} })

const ops: Record<string, string> = {}
cargar()
let api: typeof postComentariosDiff = postComentariosDiff

export function setComentariosApi(f: typeof api): void {
  api = f
}

function cargar(): void {
  try {
    const crudo = JSON.parse(localStorage.getItem(KEY) || '{}')
    const raw = crudo && typeof crudo === 'object' && !Array.isArray(crudo) && crudo.lista && typeof crudo.lista === 'object' ? crudo : { lista: crudo, ops: {} }
    for (const [sid, lista] of Object.entries(raw.lista as Record<string, unknown>)) {
      if (!Array.isArray(lista)) continue
      const ok = lista.filter(
        (c): c is ComentarioDiff =>
          !!c && typeof c.id === 'string' && typeof c.path === 'string' && typeof c.texto === 'string' &&
          (c.lado === 'nuevo' || c.lado === 'viejo') && Number.isInteger(c.desde) && Number.isInteger(c.hasta),
      )
      if (!ok.length) continue
      diffComentarios.porSesion[sid] = ok.slice(0, MAX_COMENTARIOS)
      const op = raw.ops?.[sid]
      if (typeof op === 'string' && /^[A-Za-z0-9_-]{8,64}$/.test(op)) ops[sid] = op
    }
  } catch {
    /* storage ilegible: se arranca vacío */
  }
}

function guardar() {
  try {
    localStorage.setItem(KEY, JSON.stringify({ lista: diffComentarios.porSesion, ops }))
  } catch {
    /* sin storage: queda en memoria */
  }
}

const tocado = (sid: string) => {
  // Con un envío en vuelo no se toca la fase ni el id: así no se rehabilita Mandar ni se reenvía con otro id.
  if (faseDe(sid).fase !== 'enviando') {
    delete ops[sid]
    diffComentarios.estado[sid] = { fase: 'idle', error: '' }
  }
  if (!diffComentarios.porSesion[sid]?.length) delete diffComentarios.porSesion[sid]
  guardar()
}

const nuevoId = (prefijo: string) => `${prefijo}${crypto.randomUUID().replace(/-/g, '')}`.slice(0, 32)

export const pendientes = (sid: string): ComentarioDiff[] => diffComentarios.porSesion[sid] ?? []
export const faseDe = (sid: string) => diffComentarios.estado[sid] ?? { fase: 'idle' as Fase, error: '' }

/** Devuelve el comentario agregado, o null si ya hay MAX_COMENTARIOS. */
export function agregar(sid: string, c: Omit<ComentarioDiff, 'id'>): ComentarioDiff | null {
  const lista = diffComentarios.porSesion[sid] ?? []
  if (lista.length >= MAX_COMENTARIOS) return null
  const nuevo = { ...c, id: nuevoId('c') }
  diffComentarios.porSesion[sid] = [...lista, nuevo]
  tocado(sid)
  return nuevo
}

export function editar(sid: string, id: string, texto: string): void {
  const lista = diffComentarios.porSesion[sid]
  if (!lista) return
  diffComentarios.porSesion[sid] = lista.map((c) => (c.id === id ? { ...c, texto } : c))
  tocado(sid)
}

export function quitar(sid: string, id: string): void {
  const lista = diffComentarios.porSesion[sid]
  if (!lista) return
  diffComentarios.porSesion[sid] = lista.filter((c) => c.id !== id)
  tocado(sid)
}

/** Manda la tanda en un solo mensaje. El id de operación se reusa mientras la lista no cambie. */
export async function mandar(sid: string): Promise<boolean> {
  const lista = pendientes(sid)
  if (!lista.length || faseDe(sid).fase === 'enviando') return false
  const id = (ops[sid] ??= nuevoId('cd'))
  const idsEnviados = new Set(lista.map((c) => c.id))
  guardar()
  diffComentarios.estado[sid] = { fase: 'enviando', error: '' }
  try {
    await api(sid, {
      id,
      comentarios: lista.map(({ path, lado, desde, hasta, fragmento, texto }) => ({ path, lado, desde, hasta, fragmento, texto })),
    })
  } catch (e) {
    const repetido = e instanceof ApiError && e.status === 409 && e.detail.startsWith(YA_SE_MANDO)
    if (!repetido) {
      diffComentarios.estado[sid] = { fase: 'error', error: e instanceof ApiError && e.detail ? e.detail : 'No pude mandar los comentarios' }
      return false
    }
  }
  delete ops[sid]
  const resto = pendientes(sid).filter((c) => !idsEnviados.has(c.id))
  if (resto.length) diffComentarios.porSesion[sid] = resto
  else delete diffComentarios.porSesion[sid]
  diffComentarios.estado[sid] = { fase: 'ok', error: '' }
  guardar()
  return true
}
