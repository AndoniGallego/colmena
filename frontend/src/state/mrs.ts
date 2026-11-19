import { computed, reactive, ref, watch } from 'vue'
import { ApiError } from '../api/types'
import { httpMrsApi, REF_RE, type Mr, type MrDestino, type MrDetalle, type MrsApi } from '../api/mrsApi'
import { auth, mrsEvent } from './app'
import { marcarDestino } from './avisos'
import { historyEntry } from '../lib/historyEntry'
import { desktop } from '../lib/viewport'

let api: MrsApi = httpMrsApi
export const mrsApi = () => api
export const setMrsApi = (next: MrsApi) => (api = next)

/** Pestaña visible (pager móvil o capa de escritorio). */
export const mrsVisible = ref(false)
/** Pedido de abrir la sección en un MR (aviso, chip del tablero, link). */
export const mrsRequest = ref<{ ref: string; n: number } | null>(null)
/** Pedido de abrir el alta de un MR desde una sesión. */
export const crearRequest = ref<{ sessionId: string; n: number } | null>(null)

export type Accion = 'aprobar' | 'desaprobar' | 'comentar' | 'reintentar' | 'reviewers' | 'draft' | 'listo' | 'mergear' | 'cerrar' | 'pausa' | 'pedir'

export const mrs = reactive({
  items: [] as Mr[],
  sesiones: {} as Record<string, string>,
  error: '',
  disponible: true,
  habilitado: false,
  actualizado: 0,
  loaded: false,
  loading: false,
  refreshing: false,
  sel: null as string | null,
  detalle: null as MrDetalle | null,
  detLoading: false,
  detError: '',
  busy: null as Accion | null,
  filtro: 'todos' as 'todos' | 'autor' | 'revisor',
  errConfirm: '',
  okMsg: '',
  pausaErr: '',
})

export const mrsPin = reactive({
  open: false,
  accion: 'mergear' as 'mergear' | 'cerrar',
  busy: false,
  error: null as string | null,
  lockedUntil: null as number | null,
  listo: false,
  listoTxt: '',
})

export const mrSel = computed(() => mrs.items.find((m) => m.ref === mrs.sel) ?? null)
const noPausados = (items: Mr[]) => items.filter((m) => !m.pausado)
export const visibles = computed(() => {
  const base = noPausados(mrs.items)
  return mrs.filtro === 'todos' ? base : base.filter((m) => m.rol === mrs.filtro)
})
export const enPausa = computed(() => {
  const base = mrs.items.filter((m) => m.pausado)
  return mrs.filtro === 'todos' ? base : base.filter((m) => m.rol === mrs.filtro)
})
export const cuenta = computed(() => ({
  autor: mrs.items.filter((m) => m.rol === 'autor' && !m.pausado).length,
  revisor: mrs.items.filter((m) => m.rol === 'revisor' && !m.pausado).length,
  pausa: mrs.items.filter((m) => m.pausado).length,
}))
/** Lo que pide atención: un pipeline mío roto, comentarios nuevos o una revisión que todavía no aprobé. */
export const pendientesMrs = computed(
  () => mrs.items.filter((m) => !m.pausado && ((m.rol === 'autor' && (m.pipeline.estado === 'fallo' || m.comentarios_nuevos > 0)) || (m.rol === 'revisor' && !m.aprobaciones.yo && !m.draft))).length,
)

/** Sesión abierta asociada al MR (la que lo creó o trabaja en su rama), si hay. */
export function sesionDeMr(ref: string): string | null {
  return Object.entries(mrs.sesiones).find(([, r]) => r === ref)?.[0] ?? null
}

export function mrDeSesion(sessionId: string | null | undefined): Mr | null {
  const ref = sessionId ? mrs.sesiones[sessionId] : ''
  return ref ? (mrs.items.find((m) => m.ref === ref) ?? null) : null
}

const mensaje = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

let seq = 0
let ultimaCarga = 0
const RECIEN = 5000
export async function cargarMrs(silencioso = false, manual = false) {
  const mine = ++seq
  if (manual) mrs.refreshing = true
  else if (!silencioso || !mrs.loaded) mrs.loading = true
  try {
    const out = manual ? await api.refrescar() : await api.listar()
    if (mine !== seq) return
    mrs.items = out.items
    mrs.sesiones = out.sesiones
    mrs.error = out.error
    mrs.disponible = out.disponible
    mrs.habilitado = out.habilitado !== false
    if (!mrs.habilitado) {
      mrs.items = []
      mrs.sesiones = {}
      mrs.loaded = true
      return
    }
    mrs.actualizado = out.actualizado
    mrs.loaded = true
    ultimaCarga = Date.now()
  } catch (e) {
    if (mine !== seq) return
    mrs.error = mensaje(e, 'No pude leer tus MRs')
    if (e instanceof ApiError && e.status === 503) mrs.disponible = false
  } finally {
    if (mine === seq) {
      mrs.loading = false
      mrs.refreshing = false
    }
  }
}

let detSeq = 0
const detCache = new Map<string, MrDetalle>()
const DET_CACHE_MAX = 20
export async function cargarDetalle(ref = mrs.sel, silencioso = false) {
  if (!ref) return
  const mine = ++detSeq
  const previo = detCache.get(ref)
  if (previo && mrs.detalle?.ref !== ref) {
    // Se muestra lo último que se vio mientras llega lo nuevo; los campos de la lista son más frescos.
    mrs.detalle = { ...previo, ...(mrs.items.find((m) => m.ref === ref) ?? {}) }
    silencioso = true
  }
  if (!silencioso || mrs.detalle?.ref !== ref) {
    mrs.detLoading = true
    if (mrs.detalle?.ref !== ref) mrs.detalle = null
  }
  mrs.detError = ''
  try {
    const d = await api.detalle(ref)
    if (mine !== detSeq) return
    mrs.detalle = d
    detCache.delete(ref)
    detCache.set(ref, d)
    if (detCache.size > DET_CACHE_MAX) detCache.delete(detCache.keys().next().value as string)
    const item = mrs.items.find((m) => m.ref === ref)
    if (item) {
      const { descripcion: _d, jobs: _j, hilos: _h, actividad: _ac, archivos: _a, ...fresco } = d
      Object.assign(item, fresco, { comentarios_nuevos: 0 })
    }
  } catch (e) {
    if (mine !== detSeq) return
    mrs.detError = mensaje(e, 'No pude abrir el MR')
  } finally {
    if (mine === detSeq) mrs.detLoading = false
  }
}

function soltarMr() {
  mrs.sel = null
  mrs.detalle = null
  mrs.detError = ''
  mrs.okMsg = ''
  detSeq++
}

/** En el celu el detalle tapa la lista: vive en su propia entrada de historial para que Atrás y el gesto de volver lo cierren. */
const navMr = historyEntry('orqMr', soltarMr)

export function abrirMr(ref: string) {
  if (!REF_RE.test(ref)) return
  mrs.sel = ref
  if (!desktop.value) navMr.push(ref)
  void cargarDetalle(ref)
  void marcarDestino({ mr: ref })
}

export function cerrarMr() {
  if (!mrs.sel) return
  if (!navMr.back()) soltarMr()
}

/** Desde un aviso o el chip del tablero: abre la sección y el MR. */
export function irAMr(ref: string) {
  if (!REF_RE.test(ref)) return
  mrsRequest.value = { ref, n: Date.now() }
  abrirMr(ref)
}

async function accion<T>(nombre: Accion, ref: string, fn: () => Promise<T>, recargar = true): Promise<boolean> {
  if (mrs.busy) return false
  mrs.busy = nombre
  mrs.errConfirm = ''
  mrs.okMsg = ''
  try {
    await fn()
    if (recargar) void cargarDetalle(ref, true)
    return true
  } catch (e) {
    mrs.errConfirm = mensaje(e, 'GitLab no respondió')
    return false
  } finally {
    mrs.busy = null
  }
}

export const aprobar = (ref: string, si: boolean) => accion(si ? 'aprobar' : 'desaprobar', ref, () => api.aprobar(ref, si))
export const comentar = (ref: string, texto: string) => accion('comentar', ref, () => api.comentar(ref, texto))
export const reintentar = (ref: string, cual: { pipeline_id: number } | { job_id: number }) =>
  accion('reintentar', ref, () => api.reintentar(ref, cual))
export const cambiarReviewers = (ref: string, usernames: string[]) => accion('reviewers', ref, () => api.reviewers(ref, usernames))
export const marcarDraft = (ref: string, draft: boolean) => accion(draft ? 'draft' : 'listo', ref, () => api.draft(ref, draft))

export async function pedirActualizacion(ref: string): Promise<boolean> {
  const ok = await accion('pedir', ref, () => api.pedirActualizar(ref), false)
  if (ok) mrs.okMsg = 'Se lo pedí a la sesión.'
  return ok
}

export type EnvioASesion = { tipo: 'job'; id: number } | { tipo: 'hilo'; id: string }
const claveEnvio = (c: EnvioASesion) => `${c.tipo}:${c.id}`

/** Qué botón «Mandar a la sesión» está ocupado, cuál acaba de mandar (3 s) y cuál falló. */
export const envio = reactive({ cual: '', hecho: '', error: { clave: '', msg: '' } })
export const mrsDestino = reactive({
  open: false,
  ref: '',
  cual: null as EnvioASesion | null,
  sesiones: [] as MrDestino[],
  sugerida: null as string | null,
  busy: false,
  error: '',
})

const HECHO_MS = 3000
let hechoTimer: ReturnType<typeof setTimeout> | undefined

function enviarA(ref: string, cual: EnvioASesion, sessionId: string): Promise<void> {
  return cual.tipo === 'job' ? api.jobASesion(ref, cual.id, sessionId) : api.hiloASesion(ref, cual.id, sessionId)
}

function marcarHecho(clave: string) {
  envio.hecho = clave
  clearTimeout(hechoTimer)
  hechoTimer = setTimeout(() => {
    if (envio.hecho === clave) envio.hecho = ''
  }, HECHO_MS)
}

export function cerrarDestino() {
  mrsDestino.open = false
  mrsDestino.busy = false
  mrsDestino.error = ''
  mrsDestino.cual = null
  mrsDestino.sesiones = []
}

/** Un toque: con una sola sesión asociada al MR se manda directo; si no, se elige en la hoja. */
export async function mandarASesion(ref: string, cual: EnvioASesion): Promise<void> {
  if (envio.cual) return
  const clave = claveEnvio(cual)
  envio.cual = clave
  envio.error = { clave: '', msg: '' }
  try {
    const d = await api.destinos(ref)
    const asociadas = d.sesiones.filter((s) => s.asociada)
    if (!d.sesiones.length) {
      envio.error = { clave, msg: 'No hay una sesión de Claude abierta para mandárselo.' }
    } else if (asociadas.length === 1) {
      await enviarA(ref, cual, asociadas[0].session_id)
      marcarHecho(clave)
    } else {
      const sugerida = d.sugerida
      mrsDestino.ref = ref
      mrsDestino.cual = cual
      mrsDestino.sugerida = sugerida
      mrsDestino.sesiones = [...d.sesiones].sort((a, b) => Number(b.session_id === sugerida) - Number(a.session_id === sugerida))
      mrsDestino.error = ''
      mrsDestino.busy = false
      mrsDestino.open = true
    }
  } catch (e) {
    envio.error = { clave, msg: mensaje(e, 'No pude mandarlo a la sesión') }
  } finally {
    envio.cual = ''
  }
}

export async function elegirDestino(sessionId: string): Promise<void> {
  const cual = mrsDestino.cual
  if (!cual || mrsDestino.busy) return
  mrsDestino.busy = true
  mrsDestino.error = ''
  try {
    await enviarA(mrsDestino.ref, cual, sessionId)
    marcarHecho(claveEnvio(cual))
    cerrarDestino()
  } catch (e) {
    mrsDestino.error = mensaje(e, 'No pude mandarlo a la sesión')
    mrsDestino.busy = false
  }
}

export async function pausar(ref: string, si: boolean): Promise<boolean> {
  if (mrs.busy) return false
  const item = mrs.items.find((m) => m.ref === ref)
  if (!item) return false
  const prev = item.pausado
  const detPrev = mrs.detalle?.ref === ref ? mrs.detalle.pausado : undefined
  ++seq
  mrs.busy = 'pausa'
  item.pausado = si
  if (mrs.detalle?.ref === ref) mrs.detalle.pausado = si
  try {
    await api.pausar(ref, si)
    mrs.pausaErr = ''
    return true
  } catch (e) {
    item.pausado = prev
    if (mrs.detalle?.ref === ref && detPrev !== undefined) mrs.detalle.pausado = detPrev
    mrs.pausaErr = mensaje(e, 'No pude guardar la pausa')
    return false
  } finally {
    mrs.busy = null
  }
}

export function pedirPin(accionPin: 'mergear' | 'cerrar') {
  mrsPin.accion = accionPin
  mrsPin.error = null
  mrsPin.open = true
}

export async function confirmarPin(pin: string): Promise<void> {
  const ref = mrs.sel
  const det = mrs.detalle
  if (!ref || mrsPin.busy) return
  mrsPin.busy = true
  mrsPin.error = null
  try {
    if (mrsPin.accion === 'mergear') await api.mergear(ref, pin, det?.sha || mrSel.value?.sha || '')
    else await api.cerrar(ref, pin)
    mrsPin.listoTxt = mrsPin.accion === 'mergear' ? 'MR mergeado' : 'MR cerrado'
    mrsPin.listo = true
    setTimeout(() => {
      mrsPin.listo = false
      mrsPin.open = false
      mrs.items = mrs.items.filter((m) => m.ref !== ref)
      detCache.delete(ref)
      cerrarMr()
    }, 1100)
  } catch (e) {
    if (e instanceof ApiError && e.status === 429) {
      mrsPin.lockedUntil = Date.now() + (e.retryAfter ?? 600) * 1000
      mrsPin.error = 'Demasiados intentos.'
    } else if (e instanceof ApiError && e.status === 403 && e.message === 'PIN incorrecto') {
      mrsPin.error = 'PIN incorrecto.'
    } else {
      mrsPin.error = mensaje(e, 'GitLab no respondió')
    }
  } finally {
    mrsPin.busy = false
  }
}

export function initMrsNav() {
  const params = new URLSearchParams(location.search)
  const ref = params.get('mr')
  if (!ref) return
  params.delete('mr')
  try {
    const rest = params.toString()
    history.replaceState(history.state, '', `${location.pathname}${rest ? `?${rest}` : ''}${location.hash}`)
  } catch {
    /* sin history: el link se consume igual */
  }
  if (REF_RE.test(ref)) pendiente = ref
}

let pendiente: string | null = null

watch(auth, (a) => {
  if (a !== 'ready') return
  void cargarMrs(true)
  if (pendiente) {
    const ref = pendiente
    pendiente = null
    irAMr(ref)
  }
})

watch(mrsEvent, () => {
  if (auth.value !== 'ready') return
  void cargarMrs(true)
  if (mrsVisible.value && mrs.sel) void cargarDetalle(mrs.sel, true)
})

watch(mrsVisible, (on) => {
  if (on && !mrs.loading && !(mrs.loaded && Date.now() - ultimaCarga < RECIEN)) void cargarMrs(mrs.loaded)
})
