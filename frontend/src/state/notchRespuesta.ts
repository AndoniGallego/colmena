import { reactive, ref, watch } from 'vue'
import { ApiError, type PreguntaSesion } from '../api/types'
import { huellaOf, otroProblem, type Outcome } from '../lib/dialogo'
import { replyText } from '../lib/opciones'
import { formaPedido, formaRespuesta, type FormaRespuesta } from '../lib/notchRespuesta'
import { newId } from '../lib/reply'
import type { SesionNotch } from '../lib/notchCeldas'
import { getPregunta, responderPregunta } from './app'
import { answerPermiso, answerPregunta, decidirPedido, dlg, loadDialog } from './dialogo'
import { enviadas, sesiones } from './notch'
import { abrirPedidoPestana, pedidosDeSesion, pedidosPestana, rechazarPedidoPestana } from './pedidosPestana'

export const MENSAJE_CAMBIO = 'La sesión cambió, abrila en Colmena'
export const MENSAJE_ENVIADO = '✓ Enviado a la sesión'
export const MENSAJE_PREGUNTA_CAMBIO = 'La pregunta cambió'
export const MENSAJE_YA_MANDADO = 'Ya se mandó'

export type FaseFila = 'idle' | 'enviando' | 'enviado' | 'cambio' | 'error'
export interface EstadoFila {
  fase: FaseFila
  mensaje?: string
}

export const filas = reactive<Record<string, EstadoFila>>({})
export const activa = ref<string | null>(null)

interface EstadoPregunta {
  data: PreguntaSesion | null
  cargando: boolean
  /** El servidor no tiene pregunta vigente: se contesta por el diálogo como antes. */
  caida?: boolean
}
const intentos = new Map<string, { sig: string; texto: string; id: string }>()
const preguntas = reactive<Record<string, EstadoPregunta>>({})
const tokensPregunta = new Map<string, number>()

const conPregunta = (s: SesionNotch) => s.motivo === 'pregunta' && (s.preguntas ?? 0) > 0

/** Mientras el usuario escribe en el aviso, no recoger ni cerrar por gracia. */
export const retenerRespuestaAviso = ref(false)

const reevaluarTrasRetencion: (() => void)[] = []

export function alSoltarRetencionAviso(fn: () => void): void {
  reevaluarTrasRetencion.push(fn)
}

export function marcarRetenerRespuestaAviso(retener: boolean): void {
  retenerRespuestaAviso.value = retener
  if (!retener) {
    for (const fn of reevaluarTrasRetencion) fn()
  }
}

const ENVIADO_MS = 2200
const CAMBIO_MS = 6000
const timers = new Map<string, ReturnType<typeof setTimeout>>()
const anclaPregunta = new Map<string, string>()

function limpiarTimer(sid: string) {
  const t = timers.get(sid)
  if (t) {
    clearTimeout(t)
    timers.delete(sid)
  }
}

function anclaDe(sid: string): string {
  const p = preguntas[sid]?.data
  if (p) return `p:${p.sig}`
  if (dlg.sessionId === sid && dlg.view) return `d:${huellaOf(dlg.view) ?? ''}`
  return ''
}

function programarVueltaIdle(sid: string) {
  limpiarTimer(sid)
  timers.set(
    sid,
    setTimeout(() => {
      const f = filas[sid]?.fase
      if (f === 'cambio' || f === 'error') filas[sid] = { fase: 'idle' }
      timers.delete(sid)
      anclaPregunta.delete(sid)
    }, CAMBIO_MS),
  )
}

function revisarAncla(sid: string) {
  const f = filas[sid]?.fase
  if (f !== 'cambio' && f !== 'error') return
  if (anclaPregunta.get(sid) !== anclaDe(sid)) {
    limpiarTimer(sid)
    filas[sid] = { fase: 'idle' }
    anclaPregunta.delete(sid)
  }
}

function marcarEnviado(sid: string) {
  enviadas.set(sid, Date.now())
  filas[sid] = { fase: 'enviado' }
  anclaPregunta.delete(sid)
  limpiarTimer(sid)
  timers.set(
    sid,
    setTimeout(() => {
      if (filas[sid]?.fase === 'enviado') filas[sid] = { fase: 'idle' }
      timers.delete(sid)
    }, ENVIADO_MS),
  )
}

function marcarCambio(sid: string, mensaje = MENSAJE_CAMBIO) {
  anclaPregunta.set(sid, anclaDe(sid))
  limpiarTimer(sid)
  filas[sid] = { fase: 'cambio', mensaje }
  programarVueltaIdle(sid)
}

function marcarError(sid: string, mensaje: string) {
  anclaPregunta.set(sid, anclaDe(sid))
  limpiarTimer(sid)
  filas[sid] = { fase: 'error', mensaje }
  programarVueltaIdle(sid)
}

async function cargarPregunta(sid: string): Promise<void> {
  const mine = (tokensPregunta.get(sid) ?? 0) + 1
  tokensPregunta.set(sid, mine)
  preguntas[sid] = { data: preguntas[sid]?.data ?? null, cargando: true }
  let data: PreguntaSesion | null = null
  let caida = false
  try {
    data = await getPregunta(sid)
  } catch (e) {
    caida = e instanceof ApiError && e.status === 404
  }
  if (tokensPregunta.get(sid) !== mine) return
  preguntas[sid] = { data, cargando: false, caida }
  if (caida) void loadDialog(sid)
  revisarAncla(sid)
}

export function recargar(sid: string, s?: SesionNotch): void {
  const ses = s ?? sesiones.value.find((x) => x.session_id === sid)
  if (ses?.motivo === 'pedido') return
  if (ses && conPregunta(ses)) void cargarPregunta(sid)
  else void loadDialog(sid)
}

export function activar(sessionId: string, s?: SesionNotch): void {
  activa.value = sessionId
  recargar(sessionId, s)
}

export function formaDe(s: SesionNotch): FormaRespuesta {
  if (s.motivo === 'pedido') {
    const p = pedidosDeSesion(s.session_id)[0]
    return p ? formaPedido(p, pedidosPestana.porId[p.id]) : { tipo: 'abrir', motivo: 'Abrila en Colmena' }
  }
  const p = activa.value === s.session_id ? preguntas[s.session_id] : undefined
  if (conPregunta(s) && !p?.caida) {
    return formaRespuesta(null, !!p && p.cargando && !p.data, p?.data ?? null)
  }
  const view = activa.value === s.session_id ? dlg.view : null
  const cargando = activa.value === s.session_id && dlg.loading && !dlg.view
  return formaRespuesta(view, cargando)
}

async function terminar(sid: string, out: Outcome | null): Promise<void> {
  if (out === null) {
    if (dlg.phase === 'done') marcarEnviado(sid)
    else filas[sid] = { fase: 'idle' }
    return
  }
  const o = out
  switch (o.kind) {
    case 'done':
      marcarEnviado(sid)
      break
    case 'stale':
      marcarCambio(sid)
      break
    case 'half':
    case 'error':
      marcarError(sid, o.message)
      break
    default:
      filas[sid] = { fase: 'idle' }
  }
}

const enVuelo = new Set<string>()
const YA_MANDADO = /ya se mand|ya haya llegado/i

async function enviar(sid: string, fn: () => Promise<unknown>, sesion = false): Promise<void> {
  if (enVuelo.has(sid) || filas[sid]?.fase === 'enviando') return
  enVuelo.add(sid)
  filas[sid] = { fase: 'enviando' }
  try {
    const out = await fn()
    await terminar(sid, out as never)
  } catch (e) {
    if (e instanceof ApiError && e.status === 409) {
      if (!sesion) marcarCambio(sid)
      else if (e.detail === 'YA_CONTESTADA') {
        intentos.delete(sid)
        marcarCambio(sid, MENSAJE_PREGUNTA_CAMBIO)
        void cargarPregunta(sid)
      } else if (YA_MANDADO.test(e.detail)) marcarCambio(sid, MENSAJE_YA_MANDADO)
      else marcarError(sid, e.detail)
    } else marcarError(sid, e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor')
  } finally {
    enVuelo.delete(sid)
  }
}

async function responderSesion(s: SesionNotch, texto: string): Promise<void> {
  const sid = s.session_id
  const p = preguntas[sid]?.data
  if (!p) return
  let intento = intentos.get(sid)
  if (!intento || intento.sig !== p.sig || intento.texto !== texto) {
    intento = { sig: p.sig, texto, id: newId() }
    intentos.set(sid, intento)
  }
  const { id } = intento
  await enviar(
    sid,
    async () => {
      await responderPregunta(sid, { id, sig: p.sig, texto })
      intentos.delete(sid)
      tokensPregunta.set(sid, (tokensPregunta.get(sid) ?? 0) + 1)
      delete preguntas[sid]
      return { kind: 'done' as const }
    },
    true,
  )
}

export async function elegirOpcion(s: SesionNotch, i: number): Promise<void> {
  const forma = formaDe(s)
  if (forma.tipo !== 'opciones') return
  if (forma.via === 'sesion') {
    await responderSesion(s, replyText(i + 1, forma.opciones[i] ?? ''))
    return
  }
  await enviar(s.session_id, async () => {
    activa.value = s.session_id
    return answerPregunta({ opciones: [[i]] })
  })
}

export async function mandarTexto(s: SesionNotch, texto: string): Promise<void> {
  const forma = formaDe(s)
  if (forma.tipo === 'opciones' && forma.via === 'sesion') {
    await responderSesion(s, texto)
    return
  }
  if (forma.tipo === 'opciones') {
    const err = otroProblem(texto)
    if (err) {
      marcarError(s.session_id, err)
      return
    }
  }
  await enviar(s.session_id, async () => {
    if (forma.tipo === 'opciones') {
      activa.value = s.session_id
      return answerPregunta({ otro: texto })
    }
    return { kind: 'nada' as const }
  })
}

export async function resolverPermiso(s: SesionNotch, accion: 'permitir' | 'rechazar'): Promise<void> {
  const forma = formaDe(s)
  if (forma.tipo !== 'permiso') return
  await enviar(s.session_id, async () => {
    activa.value = s.session_id
    if (forma.via === 'pedido' && forma.pedidoId) {
      return decidirPedido(forma.pedidoId, accion === 'permitir' ? 'permitir' : 'rechazar')
    }
    return answerPermiso(accion === 'permitir' ? 'si' : 'no')
  })
}

/** `pedidoId` es el que dibujó la fila: si ya no es el primero pendiente de la sesión, no se toca nada. */
export async function resolverPedido(s: SesionNotch, accion: 'aceptar' | 'rechazar', pedidoId: string): Promise<void> {
  if (s.motivo !== 'pedido' || pedidosDeSesion(s.session_id)[0]?.id !== pedidoId) return
  if (accion === 'aceptar') await abrirPedidoPestana(pedidoId)
  else await rechazarPedidoPestana(pedidoId)
}

const vistoSesion = ref<{ sid: string; estado: string; motivo: string | null; last: string | null } | null>(
  null,
)

watch(sesiones, (list) => {
  for (const sid of Object.keys(filas)) revisarAncla(sid)

  const sid = activa.value
  if (!sid) {
    vistoSesion.value = null
    return
  }
  const s = list.find((x) => x.session_id === sid)
  if (!s) return
  const snap = { sid, estado: s.estado, motivo: s.motivo, last: s.last_activity }
  const prev = vistoSesion.value
  vistoSesion.value = snap
  if (
    prev?.sid === sid &&
    (prev.estado !== snap.estado || prev.motivo !== snap.motivo || prev.last !== snap.last)
  ) {
    const f = filas[sid]?.fase
    if (f === 'cambio' || f === 'error') {
      limpiarTimer(sid)
      filas[sid] = { fase: 'idle' }
      anclaPregunta.delete(sid)
    }
  }
})

watch(
  () => dlg.view && activa.value && dlg.sessionId === activa.value ? huellaOf(dlg.view) : null,
  () => {
    const sid = activa.value
    if (sid) revisarAncla(sid)
  },
)
