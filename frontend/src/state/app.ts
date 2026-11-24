import { reactive, ref, shallowRef } from 'vue'
import { ApiError, type Api, type Digest, type Guardado, type PedidoPermiso, type PedidoPestanaEstado, type SessionEvent } from '../api/types'
import type { ClaudeUso } from '../lib/usoClaude'
import { boardReducer, initialBoardState, type BoardAction, type BoardState } from './boardReducer'
import { findFirst, trackAttention, type AttentionKind } from '../lib/order'
import { noteBuild } from './update'
import { mensajeError } from '../lib/errores'
import { desktop } from '../lib/viewport'
import { manejarAbrirTerminalSse } from './abrirTerminalSse'

export type AuthState = 'checking' | 'login' | 'forbidden' | 'offline' | 'ready'

interface DigestEntry {
  loading: boolean
  data: Digest | null
  error: string | null
  fetchedAt: number
}

let api: Api

export interface ArranqueOpts {
  presencia?: boolean
  ligero?: boolean
  pcNudo?: boolean
  /** Ventana "Reunión" de la app de Windows: sigue la reunión pero no atiende al nudo, la guía ni el lector. */
  vistaReunion?: boolean
}

let arranqueOpts: ArranqueOpts = {}
let salirNudoDe = ''

/** La página del notch corre dentro de la app de Windows: ahí existe el panel de Reunión. */
export const pcNudoActivo = ref(false)

export const auth = ref<AuthState>('checking')

// ---------- board ----------
export const boardState = shallowRef<BoardState>(initialBoardState())
let transitionTimer: ReturnType<typeof setTimeout> | undefined
function dispatch(action: BoardAction) {
  if (action.type === 'board') trackAttention(action.board.workspaces)
  boardState.value = boardReducer(boardState.value, action)
  if (action.type === 'board' && Object.keys(boardState.value.transitions).length) {
    clearTimeout(transitionTimer)
    transitionTimer = setTimeout(() => dispatch({ type: 'transitions/clear' }), 2400)
  }
}

let unsubscribe: (() => void) | null = null

/** Last transcript change announced by the server; the open session view reacts to it. */
export const sessionEvent = shallowRef<SessionEvent | null>(null)
export const libraryEvent = shallowRef<{ ids: string[]; n: number } | null>(null)
let libraryEventN = 0
/** Último aviso nuevo anunciado por el servidor: el historial de avisos se refresca. */
export const avisoEvent = shallowRef<{ id: number; n: number } | null>(null)
let avisoEventN = 0
export const pedidoPestanaEvent = shallowRef<{ id: string; estado: PedidoPestanaEstado; n: number } | null>(null)
let pedidoPestanaEventN = 0
/** Otro dispositivo marcó avisos: cerrar tags y refrescar el contador. */
export const avisosLeidosEvent = shallowRef<{ tags: string[]; n: number } | null>(null)
let avisosLeidosEventN = 0
/** Otro dispositivo cambió el orden manual del tablero. */
export const ordenTableroEvent = shallowRef<{ orden: string[]; n: number } | null>(null)
let ordenTableroEventN = 0
export const ordenPestanasEvent = shallowRef<{ grupo: string; orden: string[]; n: number } | null>(null)
let ordenPestanasEventN = 0
export const plegadasEvent = shallowRef<{ plegadas: string[]; n: number } | null>(null)
let plegadasEventN = 0
export const silenciadasEvent = shallowRef<{ silenciadas: string[]; n: number } | null>(null)
let silenciadasEventN = 0
/** El servidor terminó un refresco de MRs: la sección vuelve a pedir la lista. */
export const mrsEvent = ref(0)
/** Cierres esperando que las sesiones guarden en Engram, por id de lote; el servidor los empuja en cada cambio. */
export const guardados = reactive<Record<string, Guardado>>({})
function startBoard() {
  unsubscribe?.()
  unsubscribe = api.subscribeBoard({
    onBoard: (b) => dispatch({ type: 'board', board: b }),
    onState: (s) => dispatch({ type: 'connection', state: s }),
    onSession: (e) => (sessionEvent.value = e),
    onLibrary: (ids) => (libraryEvent.value = { ids, n: ++libraryEventN }),
    onBuild: noteBuild,
    onAviso: (id) => (avisoEvent.value = { id, n: ++avisoEventN }),
    onPedidoPestana: (e) => (pedidoPestanaEvent.value = { ...e, n: ++pedidoPestanaEventN }),
    onAvisosLeidos: (tags) => (avisosLeidosEvent.value = { tags, n: ++avisosLeidosEventN }),
    onOrdenTablero: (orden) => (ordenTableroEvent.value = { orden, n: ++ordenTableroEventN }),
    onOrdenPestanas: (e) => (ordenPestanasEvent.value = { ...e, n: ++ordenPestanasEventN }),
    onPlegadas: (plegadas) => (plegadasEvent.value = { plegadas, n: ++plegadasEventN }),
    onSilenciadas: (silenciadas) => (silenciadasEvent.value = { silenciadas, n: ++silenciadasEventN }),
    onMrs: (version) => (mrsEvent.value = version),
    onNotas: (d) => void import('./notas').then((m) => m.onNotas(d)).catch(() => undefined),
    // Import diferido: dialogo carga motion, que necesita el navegador.
    onPermisos: (pedidos: PedidoPermiso[]) => {
      void import('./permisos').then((m) => m.actualizarPedidos(pedidos))
      void import('./dialogo').then((m) => m.onPermisosPedidos(pedidos))
    },
    onGuardado: (g) => (guardados[g.id] = g),
    onNudo: (orden, device) => {
      const invoke = window.__TAURI__?.core?.invoke
      if (arranqueOpts.pcNudo !== true || arranqueOpts.vistaReunion || typeof invoke !== 'function') return
      void import('../lib/nudoPuente').then((m) => {
        if (salirNudoDe !== device) {
          salirNudoDe = device
          void m
            .escucharSalirNudo(device, { listen: window.__TAURI__?.event?.listen, post: m.postJson })
            .then((ok) => {
              if (!ok && salirNudoDe === device) salirNudoDe = ''
            })
        }
        const o = m.normalizarOrdenNudo(orden)
        if (o) void m.atenderOrdenNudo(o, device, { invoke, post: m.postJson })
      }).catch((e) => console.warn('[nudo] no se pudo cargar el puente', e))
    },
    onReunion: (evento, data, device) => {
      if (arranqueOpts.pcNudo !== true) return
      void import('./reunion').then((m) => {
        m.fijarDevice(device)
        m.aplicarServidor(evento, data)
      })
    },
    onGuia: (data, device) => {
      if (arranqueOpts.pcNudo !== true || arranqueOpts.vistaReunion) return
      void import('./guia').then((m) => {
        m.fijarDevice(device)
        void m.aplicarServidorGuia(data)
      })
    },
    onPcListo: (device) => {
      if (arranqueOpts.pcNudo !== true) return
      void conectarReunion(device)
      if (!arranqueOpts.vistaReunion) void import('./guia').then((m) => m.fijarDevice(device))
    },
    onAbrirTerminal: (e) =>
      manejarAbrirTerminalSse(e, { presenciaActiva: arranqueOpts.presencia !== false, esEscritorio: desktop.value }, (paneId, titulo) => {
        void import('./terminalVivo').then((m) => m.abrirVivo(paneId, titulo))
      }),
  }, {
    presencia: arranqueOpts.presencia !== false,
    pcNudo: arranqueOpts.pcNudo === true,
    escritorio: () => desktop.value,
  })
}

let lectorReunionDe = ''
let soltarLector: (() => void) | null = null

/** Con la app de Windows: engancha el lector de subtítulos (una vez por conexión) y se pone al día con el back. */
async function conectarReunion(device: string) {
  const invoke = window.__TAURI__?.core?.invoke
  const listen = window.__TAURI__?.event?.listen
  try {
    const m = await import('./reunion')
    m.fijarDevice(device)
    if (!arranqueOpts.vistaReunion && lectorReunionDe !== device && typeof invoke === 'function' && typeof listen === 'function') {
      lectorReunionDe = device
      soltarLector?.()
      soltarLector = null
      m.fijarLector(null)
      const puente = await import('../lib/reunionPuente')
      const nuevo = await puente.conectarLector({
        listen: listen as never,
        invoke,
        post: m.postear,
        reunionId: m.idParaTexto,
        device,
        alLector: m.alLector,
      })
      soltarLector = nuevo
      m.fijarLector(nuevo)
    }
    await m.alReconectar()
  } catch (e) {
    lectorReunionDe = ''
    console.warn('[reunion] no se pudo conectar el lector', e)
  }
}

export const abrirEnPc: Api['abrirEnPc'] = (...args) => api.abrirEnPc(...args)

export const highlight = ref<{ paneId: string; n: number } | null>(null)
let highlightTimer: ReturnType<typeof setTimeout> | undefined

export const viewRequest = ref<{ view: 'board'; n: number } | null>(null)

export function showOnBoard(paneId: string) {
  viewRequest.value = { view: 'board', n: Date.now() }
  highlight.value = { paneId, n: Date.now() }
  clearTimeout(highlightTimer)
  highlightTimer = setTimeout(() => (highlight.value = null), 2600)
}

export function jumpTo(kind: AttentionKind) {
  const hit = findFirst(boardState.value.board?.workspaces ?? [], kind)
  if (hit) showOnBoard(hit.paneId)
}

export const digests = reactive<Record<string, DigestEntry>>({})

export async function loadDigest(sessionId: string, force = false) {
  const cur = digests[sessionId]
  if (cur?.loading) return
  if (cur?.data && !force && Date.now() - cur.fetchedAt < 15_000) return
  digests[sessionId] = { loading: true, data: cur?.data ?? null, error: null, fetchedAt: cur?.fetchedAt ?? 0 }
  try {
    const data = await api.getDigest(sessionId, 2)
    digests[sessionId] = { loading: false, data, error: null, fetchedAt: Date.now() }
  } catch (e) {
    digests[sessionId] = {
      loading: false,
      data: cur?.data ?? null,
      error: e instanceof ApiError && e.status === 404 ? 'No encontré el transcript de esta sesión' : 'No pude leer la sesión',
      fetchedAt: 0,
    }
  }
}

// ---------- feedback local (sin píldora global) ----------
export const stopErr = reactive<Record<string, string>>({})
export const stopOk = reactive<Record<string, boolean>>({})
export const revokeSessionsErr = ref('')

// ---------- uso de Claude (todas las sesiones) ----------
export const claudeUso = ref<ClaudeUso | null>(null)
export const claudeUsoError = ref(false)

export async function refreshClaudeUso() {
  try {
    claudeUso.value = await api.getClaudeUso()
    claudeUsoError.value = false
  } catch {
    claudeUsoError.value = !claudeUso.value
  }
}

export const ALREADY_DONE = /ya (se )?(fue )?(ejecut|mand|envi|cerr)|already/i

const chains: Record<string, Promise<unknown>> = {}
/** Sends to one pane go out one at a time so the agent gets them in the order they were typed. */
export function inOrder<T>(paneId: string, task: () => Promise<T>): Promise<T> {
  const next = (chains[paneId] ?? Promise.resolve()).then(task)
  chains[paneId] = next.catch(() => undefined)
  return next
}

export const UNCERTAIN = /ya haya llegado/i

export type MensajeOutcome = { ok: true; enCola?: boolean } | { ok: false; error: string; uncertain?: boolean }

export async function postMensaje(paneId: string, destino: string, texto: string, adjuntos: string[], id: string): Promise<MensajeOutcome> {
  try {
    await api.executeMensaje({
      id,
      pane_id: paneId,
      texto: texto.trim(),
      ...(adjuntos.length ? { adjuntos } : {}),
      origen: 'manual',
      destino,
      por_que: '',
    })
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && ALREADY_DONE.test(e.detail)) return { ok: true }
    if (e instanceof ApiError && e.status === 409 && UNCERTAIN.test(e.detail)) return { ok: false, error: e.detail, uncertain: true }
    return { ok: false, error: e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor' }
  }
  return { ok: true }
}

export const stopping = reactive<Record<string, boolean>>({})

export async function stopSession(paneId: string): Promise<boolean> {
  if (stopping[paneId]) return false
  stopping[paneId] = true
  delete stopErr[paneId]
  delete stopOk[paneId]
  try {
    await api.stopSession(paneId)
    stopOk[paneId] = true
    setTimeout(() => delete stopOk[paneId], 1200)
    return true
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401)) stopErr[paneId] = e instanceof ApiError ? e.message : mensajeError(e, 'Se cortó la conexión con el servidor')
    return false
  } finally {
    delete stopping[paneId]
  }
}

export const registroPermisos = () => api.getPermisosRegistro()

export const previewClose: Api['previewClose'] = (...args) => api.previewClose(...args)
export const executeClose: Api['executeClose'] = (...args) => api.executeClose(...args)
export const getLimpieza: Api['getLimpieza'] = (...args) => api.getLimpieza(...args)
export const previewLimpieza: Api['previewLimpieza'] = (...args) => api.previewLimpieza(...args)
export const ejecutarLimpieza: Api['ejecutarLimpieza'] = (...args) => api.ejecutarLimpieza(...args)
export const getDialog: Api['getDialog'] = (...args) => api.getDialog(...args)
export const getPregunta: Api['getPregunta'] = (...args) => api.getPregunta(...args)
export const responderPregunta: Api['responderPregunta'] = (...args) => api.responderPregunta(...args)
export const correrComando: Api['correrComando'] = (...args) => api.correrComando(...args)
export const answerDialog: Api['answerDialog'] = (...args) => api.answerDialog(...args)
export const decidirPermiso: Api['decidirPermiso'] = (...args) => api.decidirPermiso(...args)
export const getTranscript: Api['getTranscript'] = (...args) => api.getTranscript(...args)
export const getSubagentes: Api['getSubagentes'] = (...args) => api.getSubagentes(...args)
export const uploadFile: Api['uploadFile'] = (...args) => api.uploadFile(...args)
export const getVozEstado: Api['getVozEstado'] = () => api.getVozEstado()
export const transcribirVoz: Api['transcribirVoz'] = (...args) => api.transcribirVoz(...args)
export const getOrdenTablero: Api['getOrdenTablero'] = () => api.getOrdenTablero()
export const setOrdenTablero: Api['setOrdenTablero'] = (orden) => api.setOrdenTablero(orden)
export const setOrdenPestanas: Api['setOrdenPestanas'] = (grupo, orden) => api.setOrdenPestanas(grupo, orden)
export const setPlegadas: Api['setPlegadas'] = (plegadas) => api.setPlegadas(plegadas)
export const setSilencio: Api['setSilencio'] = (sid, on) => api.setSilencio(sid, on)
export const irAPc: Api['irAPc'] = (sid) => api.irAPc(sid)
export const accionGuardado: Api['accionGuardado'] = (loteId, accion) => api.accionGuardado(loteId, accion)
export const marcarAvisosDe: Api['marcarAvisosDe'] = (...args) => api.marcarAvisosDe(...args)
export const getAvisos: Api['getAvisos'] = (...args) => api.getAvisos(...args)
export const getPedidosPestana: Api['getPedidosPestana'] = () => api.getPedidosPestana()
export const abrirPedidoPestana: Api['abrirPedidoPestana'] = (id, opciones) => api.abrirPedidoPestana(id, opciones)
export const vistaCierrePedido: Api['vistaCierrePedido'] = (id) => api.vistaCierrePedido(id)
export const rechazarPedidoPestana: Api['rechazarPedidoPestana'] = (id) => api.rechazarPedidoPestana(id)
export const marcarAvisosLeidos: Api['marcarAvisosLeidos'] = (...args) => api.marcarAvisosLeidos(...args)
export const getLibrary: Api['getLibrary'] = (...args) => api.getLibrary(...args)
export const getLibraryItem: Api['getLibraryItem'] = (...args) => api.getLibraryItem(...args)
export const getLibrarySessions: Api['getLibrarySessions'] = (...args) => api.getLibrarySessions(...args)
export const getLibraryText: Api['getLibraryText'] = (...args) => api.getLibraryText(...args)
export const getLibraryCharla: Api['getLibraryCharla'] = (...args) => api.getLibraryCharla(...args)
export const getTerminalSalida: Api['getTerminalSalida'] = (...args) => api.getTerminalSalida(...args)
export const getTerminalConfig: Api['getTerminalConfig'] = () => api.getTerminalConfig()
export const getTerminalesCarpetas: Api['getTerminalesCarpetas'] = () => api.getTerminalesCarpetas()
export const postTerminalesNuevaTarea: Api['postTerminalesNuevaTarea'] = (...a) => api.postTerminalesNuevaTarea(...a)
export const postBorrarCopia: Api['postBorrarCopia'] = (...a) => api.postBorrarCopia(...a)
export const postTerminalesNueva: Api['postTerminalesNueva'] = (...a) => api.postTerminalesNueva(...a)
export const getSesionesViejas: Api['getSesionesViejas'] = (...a) => api.getSesionesViejas(...a)
export const postSesionesViejasRetomar: Api['postSesionesViejasRetomar'] = (...a) => api.postSesionesViejasRetomar(...a)
export const previewTerminal: Api['previewTerminal'] = (...a) => api.previewTerminal(...a)
export const terminalCtrlC: Api['terminalCtrlC'] = (...a) => api.terminalCtrlC(...a)
export const cerrarTerminal: Api['cerrarTerminal'] = (...a) => api.cerrarTerminal(...a)
export const renombrarTerminal: Api['renombrarTerminal'] = (...a) => api.renombrarTerminal(...a)
export const listarNotas: Api['listarNotas'] = () => api.listarNotas()
export const crearNotaApi: Api['crearNota'] = (...a) => api.crearNota(...a)
export const editarNotaApi: Api['editarNota'] = (...a) => api.editarNota(...a)
export const borrarNotaApi: Api['borrarNota'] = (...a) => api.borrarNota(...a)
export const repetirPreparar: Api['repetirPreparar'] = (...a) => api.repetirPreparar(...a)
export const repetirConfirmar: Api['repetirConfirmar'] = (...a) => api.repetirConfirmar(...a)
export const abrirVentana: Api['abrirVentana'] = (...a) => api.abrirVentana(...a)
export const cerrarVentana: Api['cerrarVentana'] = (...a) => api.cerrarVentana(...a)
export const enviarComando: Api['enviarComando'] = (...a) => api.enviarComando(...a)
export const getTerminalAuditoria: Api['getTerminalAuditoria'] = (...a) => api.getTerminalAuditoria(...a)
export const quitarLibrary: Api['quitarLibrary'] = (...args) => api.quitarLibrary(...args)
export const getMemoriaEstado: Api['getMemoriaEstado'] = () => api.getMemoriaEstado()
export const reindexarMemoria: Api['reindexarMemoria'] = () => api.reindexarMemoria()
export const borrarMemoria: Api['borrarMemoria'] = () => api.borrarMemoria()
export const getMemoriaCita: Api['getMemoriaCita'] = (...a) => api.getMemoriaCita(...a)
export const getPermisos: Api['getPermisos'] = () => api.getPermisos()

const seenTimers = new Map<string, ReturnType<typeof setTimeout>>()
/** Avisa que viste la respuesta; agrupa ráfagas por sesión y no molesta si falla. */
export function markSeen(sessionId: string) {
  clearTimeout(seenTimers.get(sessionId))
  seenTimers.set(
    sessionId,
    setTimeout(() => {
      seenTimers.delete(sessionId)
      void api.markSeen(sessionId).catch(() => undefined)
    }, 350),
  )
}

/** Da por leída la pregunta de una sesión; el tablero nuevo llega por el stream. */
export const marcarPreguntaVista: Api['marcarPreguntaVista'] = (sessionId) => api.marcarPreguntaVista(sessionId)

export const loadHandoff = (name: string) => api.getHandoff(name)

export async function revokeAllSessions(): Promise<boolean> {
  try {
    await api.revokeAll()
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401)) {
      revokeSessionsErr.value = 'No pude cerrar las sesiones'
      return false
    }
  }
  onUnauthorized()
  return true
}

// ---------- lifecycle ----------
export function init(a: Api, opts?: ArranqueOpts) {
  api = a
  arranqueOpts = opts ?? {}
  pcNudoActivo.value = arranqueOpts.pcNudo === true && !arranqueOpts.vistaReunion
}

export function onUnauthorized() {
  unsubscribe?.()
  unsubscribe = null
  if (auth.value !== 'login') auth.value = 'login'
}

export async function boot(opts: { quiet?: boolean; gate?: Promise<unknown> } = {}) {
  if (!opts.quiet) auth.value = 'checking'
  try {
    const b = await api.getBoard()
    await opts.gate
    dispatch({ type: 'board', board: b })
    auth.value = 'ready'
    startBoard()
    void import('./notas').then((m) => m.cargarNotas()).catch(() => undefined)
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) auth.value = 'login'
    else if (e instanceof ApiError && e.status === 403) auth.value = 'forbidden'
    else auth.value = 'offline'
  }
}

/** `ceremony` runs once the PIN is accepted, in parallel with the first board fetch. */
export async function login(pin: string, ceremony?: () => Promise<unknown>) {
  await api.login(pin)
  await boot({ quiet: true, gate: ceremony?.() })
}
