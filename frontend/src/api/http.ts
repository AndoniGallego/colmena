import { normalizeDialog, PIN_WRONG } from '../lib/dialogo'
import type { DialogView, PedidoPermiso, PreguntaSesion } from './types'
import { createSSEParser } from '../lib/sse'
import { AVISO_TAG_RE, normalizeAvisos, normalizeBlockers, normalizeBoard, normalizeCloseResult, normalizeGuardado, normalizeClosePreview, normalizeLimpieza, normalizeLimpiezaPreview, normalizeDigest, normalizeSubagentes, normalizeLibItem, normalizeLibListing, normalizeLibSessions, normalizeMessage, normalizeTerminalSalida, normalizeTerminalConfig, normalizeTerminalPreview, normalizeRepetirPrep, normalizeTerminalAuditoria, normalizeTranscript, normalizeUpload, normalizeVozEstado, normalizeVozResultado, normalizeMemoriaEstado, normalizeMemoriaCita, normalizePedidoPestanaEvento, normalizePedidosPestana, normalizeVistaCierrePedido } from './normalize'
import { libQuery } from '../lib/biblioteca'
import { EVENTO_CURSOR, EVENTO_PROGRAMADAS } from '../lib/tareas'
import { normalizeClaudeUso } from '../lib/usoClaude'
import { extFor } from '../lib/voz'
import { tracked } from '../lib/update'
import { deviceId } from '../lib/device'
import { ApiError, type Api, type CategoriaPermiso, type CloseBlocker, type ConfianzaPreparar, type PrepararResumen, type ConnectionState, type LimpiezaHandlers, type RegistroPermiso, type SubscribeOpts } from './types'

let mirando: string | null = null
let reportNow: (() => void) | null = null

/** The session on screen: its turn endings don't come back as reports while someone is looking at it. */
export function informarMirando(id: string | null) {
  if (id === mirando) return
  mirando = id
  reportNow?.()
}

async function errorBody(res: Response): Promise<{ detail: string; bloqueantes: CloseBlocker[]; sinCuerpo: boolean; codigo?: string; confianza?: ConfianzaPreparar }> {
  try {
    const body = await res.clone().json()
    if (typeof body?.detail === 'string') {
      const conf = body.codigo === 'requiere_confianza' && body.confianza && typeof body.confianza === 'object' ? body.confianza : undefined
      return { detail: body.detail, bloqueantes: normalizeBlockers(body.bloqueantes), sinCuerpo: false, ...(conf ? { codigo: 'requiere_confianza', confianza: normalizarConfianza(conf) } : {}) }
    }
  } catch {
    /* not json */
  }
  return { detail: res.statusText || `HTTP ${res.status}`, bloqueantes: [], sinCuerpo: true }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const send = fetch(path, {
    credentials: 'same-origin',
    ...init,
    headers: init.body instanceof FormData ? init.headers : { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  const res = await (init.method && init.method !== 'GET' ? tracked(send) : send)
  if (!res.ok) {
    const ra = Number(res.headers.get('Retry-After'))
    const { detail, bloqueantes, sinCuerpo, codigo, confianza } = await errorBody(res)
    throw new ApiError(res.status, detail, Number.isFinite(ra) && ra > 0 ? ra : null, bloqueantes, sinCuerpo, codigo, confianza)
  }
  return res
}

const str = (v: unknown) => (typeof v === 'string' ? v : '')

function normalizarConfianza(c: Record<string, unknown>): ConfianzaPreparar {
  const o = (v: unknown) => (typeof v === 'string' ? v : null)
  return {
    repo: str(c.repo),
    base: str(c.base),
    origen: str(c.origen),
    setup_toml: str(c.setup_toml),
    setup_sha256: str(c.setup_sha256),
    script: o(c.script),
    script_contenido: o(c.script_contenido),
    script_sha256: o(c.script_sha256),
    copiar: Array.isArray(c.copiar) ? c.copiar.filter((x): x is string => typeof x === 'string') : [],
    puertos: typeof c.puertos === 'number' ? c.puertos : 0,
    docker: c.docker === true,
  }
}

function normalizarPreparar(p: unknown): PrepararResumen | undefined {
  if (!p || typeof p !== 'object') return undefined
  const d = p as Record<string, unknown>
  const lista = (v: unknown) => (Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string') : [])
  return {
    puerto: typeof d.puerto === 'number' ? d.puerto : null,
    puertos: typeof d.puertos === 'number' ? d.puertos : 0,
    copiados: lista(d.copiados),
    omitidos: lista(d.omitidos),
    ...(typeof d.setup_pane_id === 'string' ? { setup_pane_id: d.setup_pane_id } : {}),
    ...(d.puertos_fijos === true ? { puertos_fijos: true } : {}),
  }
}

export function normalizePregunta(raw: unknown): PreguntaSesion {
  const o = raw && typeof raw === 'object' ? (raw as Record<string, unknown>) : {}
  const lista = Array.isArray(o.preguntas) ? o.preguntas : []
  const preguntas = lista.map((q) => {
    const qq = q && typeof q === 'object' ? (q as Record<string, unknown>) : {}
    const ops = Array.isArray(qq.opciones) ? qq.opciones : []
    return {
      pregunta: str(qq.pregunta),
      opciones: ops
        .map((x) => (x && typeof x === 'object' ? (x as Record<string, unknown>) : {}))
        .filter((x) => str(x.label))
        .map((x) => ({ label: str(x.label), detalle: str(x.detalle), recomendada: x.recomendada === true })),
    }
  })
  return { sig: str(o.sig), session_id: str(o.session_id), pane_id: str(o.pane_id), nombre: str(o.nombre), preguntas }
}

export function normalizePermisosRegistro(raw: unknown): { items: RegistroPermiso[] } {
  const list = raw && typeof raw === 'object' && Array.isArray((raw as { items?: unknown }).items) ? (raw as { items: unknown[] }).items : []
  const items: RegistroPermiso[] = []
  for (const row of list) {
    if (!row || typeof row !== 'object') continue
    const o = row as Record<string, unknown>
    const catRaw = o.categoria
    const cat: CategoriaPermiso | undefined = catRaw === 'auto' || catRaw === 'gris' || catRaw === 'usuario' ? catRaw : undefined
    const decision = o.decision === 'permitir' || o.decision === 'rechazar' || o.decision === 'siempre' ? o.decision : undefined
    if (!cat && !decision) continue
    const entrada = o.entrada && typeof o.entrada === 'object' && !Array.isArray(o.entrada) ? (o.entrada as Record<string, unknown>) : undefined
    items.push({
      hora: typeof o.hora === 'string' ? o.hora : undefined,
      categoria: cat,
      decision,
      regla_politica: typeof o.regla_politica === 'string' ? o.regla_politica : o.regla_politica == null ? null : undefined,
      motivo_politica: typeof o.motivo_politica === 'string' ? o.motivo_politica : o.motivo_politica == null ? null : undefined,
      herramienta: typeof o.herramienta === 'string' ? o.herramienta : undefined,
      entrada,
      pane_id: typeof o.pane_id === 'string' ? o.pane_id : undefined,
      session_id: typeof o.session_id === 'string' ? o.session_id : undefined,
      sesion: typeof o.sesion === 'string' ? o.sesion : o.sesion === null ? null : undefined,
      quien:
        o.quien === 'politica' || o.quien === 'usuario' || o.quien === 'centinela' ? o.quien : undefined,
      tool_use_id: typeof o.tool_use_id === 'string' ? o.tool_use_id : undefined,
      motivo_centinela:
        typeof o.motivo_centinela === 'string' ? o.motivo_centinela : o.motivo_centinela == null ? null : undefined,
      encargo_id: typeof o.encargo_id === 'string' ? o.encargo_id : undefined,
      objecion: (() => {
        const ob = o.objecion
        if (!ob || typeof ob !== 'object' || Array.isArray(ob)) return undefined
        const nota = (ob as { nota?: unknown }).nota
        if (typeof nota !== 'string' || !nota) return undefined
        const hora = (ob as { hora?: unknown }).hora
        return { nota, ...(typeof hora === 'string' ? { hora } : {}) }
      })(),
    })
  }
  return { items }
}

const json = async (path: string, init?: RequestInit) => (await request(path, init)).json()
const post = (path: string, body?: unknown) =>
  request(path, { method: 'POST', body: body === undefined ? undefined : JSON.stringify(body) })

function parseData(data: string): any {
  try {
    return JSON.parse(data)
  } catch {
    return null
  }
}

function uploadWithProgress(file: File, onProgress: (fraction: number) => void, signal: AbortSignal) {
  return new Promise<ReturnType<typeof normalizeUpload>>((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    const form = new FormData()
    form.append('file', file, file.name)
    xhr.open('POST', '/api/uploads')
    xhr.withCredentials = true
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onerror = () => reject(new ApiError(0, 'Se cortó la conexión con el servidor'))
    xhr.onabort = () => reject(new DOMException('aborted', 'AbortError'))
    xhr.onload = () => {
      let body: any = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* not json */
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(normalizeUpload(body))
      else reject(new ApiError(xhr.status, typeof body?.detail === 'string' ? body.detail : `HTTP ${xhr.status}`))
    }
    signal.addEventListener('abort', () => xhr.abort(), { once: true })
    xhr.send(form)
  })
}

const PRESENCE_RENEW_MS = 60_000

/** Eventos SSE del copiloto de reuniones. */
const EVENTOS_REUNION = ['reunion-estado', 'reunion-linea', 'reunion-respuesta', 'reunion-descartada', 'reunion-anotada', 'reunion-memoria', 'reunion-guardada'] as const
const STALE_MS = 40_000
const RESUME_MS = 8_000

/** `kindsAviso`: kinds de aviso que suman las piezas montadas. */
export function createHttpApi(onUnauthorized: () => void, kindsAviso: () => readonly string[] = () => []): Api {
  const guard = async <T>(p: Promise<T>): Promise<T> => {
    try {
      return await p
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onUnauthorized()
      throw e
    }
  }

  return {
    async login(pin) {
      await post('/api/login', { pin })
    },

    getBoard: () => guard(json('/api/board').then(normalizeBoard)),

    getOrdenTablero: () =>
      guard(
        json('/api/tablero/orden').then((raw) => {
          const o =
            raw && typeof raw === 'object' ? (raw as { orden?: unknown; pestanas?: unknown; plegadas?: unknown; silenciadas?: unknown }) : {}
          const orden = Array.isArray(o.orden) ? o.orden.filter((x): x is string => typeof x === 'string') : []
          const pestanas: Record<string, string[]> = {}
          if (o.pestanas && typeof o.pestanas === 'object' && !Array.isArray(o.pestanas)) {
            for (const [k, v] of Object.entries(o.pestanas as Record<string, unknown>)) {
              if (typeof k !== 'string' || !Array.isArray(v)) continue
              const ids = v.filter((x): x is string => typeof x === 'string')
              if (ids.length) pestanas[k] = ids
            }
          }
          const plegadas = Array.isArray(o.plegadas) ? o.plegadas.filter((x): x is string => typeof x === 'string') : []
          const silenciadas = Array.isArray(o.silenciadas) ? o.silenciadas.filter((x): x is string => typeof x === 'string') : []
          return { orden, pestanas, plegadas, silenciadas }
        }),
      ),
    getAtajos: () =>
      guard(
        json('/api/atajos').then((raw) => {
          const a = raw && typeof raw === 'object' ? (raw as { atajos?: unknown }).atajos : null
          return a && typeof a === 'object' && !Array.isArray(a) ? (a as Record<string, string>) : {}
        }),
      ),
    setAtajos: (atajos) => guard(request('/api/atajos', { method: 'PUT', body: JSON.stringify({ atajos }) }).then(() => undefined)),
    setOrdenTablero: (orden) => guard(request('/api/tablero/orden', { method: 'PUT', body: JSON.stringify({ orden }) }).then(() => undefined)),
    setOrdenPestanas: (grupo, orden) =>
      guard(request('/api/tablero/orden-pestanas', { method: 'PUT', body: JSON.stringify({ grupo, orden }) }).then(() => undefined)),
    setPlegadas: (plegadas) =>
      guard(request('/api/tablero/plegadas', { method: 'PUT', body: JSON.stringify({ plegadas }) }).then(() => undefined)),
    setSilencio: (sid, on) =>
      guard(
        request(`/api/sesiones/${encodeURIComponent(sid)}/silencio`, { method: 'PUT', body: JSON.stringify({ on }) }).then(
          () => undefined,
        ),
      ),

    getAvisos: (limite = 50, antes = 0, incluirPrueba = false) =>
      guard(
        json(`/api/avisos?limite=${limite}${antes ? `&antes=${antes}` : ''}${incluirPrueba ? '&incluir_prueba=1' : ''}`).then((raw) =>
          normalizeAvisos(raw, incluirPrueba, kindsAviso()),
        ),
      ),
    getPedidosPestana: () => guard(json('/api/pedidos-pestana').then(normalizePedidosPestana)),
    abrirPedidoPestana: (id, opciones) =>
      guard(
        post(`/api/pedidos-pestana/${encodeURIComponent(id)}/abrir`, opciones)
          .then((r) => r.json())
          .then((d) => {
            if (d?.ok !== true) throw new ApiError(0, 'Respuesta inválida')
            const pane_id = String(d.pane_id ?? '')
            if (!pane_id && d.cerrada !== true && d.guardando !== true) throw new ApiError(0, 'Respuesta inválida')
            return {
              ok: true as const,
              pane_id,
              ...(d.guardando === true ? { guardando: true } : {}),
              ...(typeof d.pegado === 'boolean' ? { pegado: d.pegado } : {}),
              ...(d.cerrada === true ? { cerrada: true } : {}),
            }
          }),
      ),
    vistaCierrePedido: (id) =>
      guard(
        post(`/api/pedidos-pestana/${encodeURIComponent(id)}/vista-cierre`)
          .then((r) => r.json())
          .then((d) => {
            const vista = normalizeVistaCierrePedido(d)
            if (!vista) throw new ApiError(0, 'Respuesta inválida')
            return vista
          }),
      ),
    rechazarPedidoPestana: (id) =>
      guard(
        post(`/api/pedidos-pestana/${encodeURIComponent(id)}/rechazar`)
          .then((r) => r.json())
          .then((d) => {
            if (d?.ok !== true) throw new ApiError(0, 'Respuesta inválida')
            return { ok: true as const }
          }),
      ),
    marcarAvisosLeidos: (hasta, endpoint) =>
      guard(
        post('/api/avisos/leidos', endpoint ? { hasta, endpoint } : { hasta })
          .then((r) => r.json())
          .then((d) => Math.max(0, Number(d?.no_leidos) || 0)),
      ),

    accionGuardado: (loteId, accion) =>
      guard(
        post('/api/close/guardado', { lote_id: loteId, accion })
          .then((r) => r.json())
          .then((d) => normalizeGuardado(d?.guardando) ?? Promise.reject(new ApiError(502, 'Respuesta inesperada'))),
      ),
    marcarAvisosDe: (filtro, endpoint) =>
      guard(
        post('/api/avisos/leidos', endpoint ? { ...filtro, endpoint } : filtro)
          .then((r) => r.json())
          .then((d) => Math.max(0, Number(d?.no_leidos) || 0)),
      ),

    subscribeBoard({ onBoard, onState, onSession, onLibrary, onBuild, onAviso, onAvisosLeidos, onOrdenTablero, onOrdenPestanas, onPlegadas, onSilenciadas, onMrs, onNotas, onPermisos, onGuardado, onAbrirTerminal, onPedidoPestana, onNudo, onGuia, onReunion, onPcListo }, opts?: SubscribeOpts) {
      const presencia = opts?.presencia !== false
      const escritorio = opts?.escritorio
      const pcNudo = opts?.pcNudo === true
      let es: EventSource | null = null
      let timer: ReturnType<typeof setTimeout> | undefined
      let watchdog: ReturnType<typeof setTimeout> | undefined
      let attempt = 0
      let closed = false
      let hiddenAt = 0
      const device = deviceId(pcNudo)
      let lastReport = 0

      // El servidor no manda push mientras la app está a la vista; solo avisamos cuando cambia (o cada ~1 min como renovación).
      const seen = () => document.visibilityState === 'visible' && (typeof document.hasFocus !== 'function' || document.hasFocus())
      const report = (visible = seen()) => {
        if (closed || !presencia) return
        lastReport = Date.now()
        void fetch('/api/presencia', {
          method: 'POST',
          credentials: 'same-origin',
          keepalive: true,
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            visible,
            device,
            ...(mirando ? { mirando } : {}),
            ...(escritorio ? { escritorio: escritorio() } : {}),
          }),
        }).catch(() => undefined)
      }
      if (presencia) reportNow = () => report()
      const onFocusChange = () => report()
      const onPageHide = () => report(false)

      // iOS congela la app en segundo plano y deja el EventSource abierto pero muerto: sin pings, se reabre.
      const feed = () => {
        clearTimeout(watchdog)
        watchdog = setTimeout(() => restart(), STALE_MS)
      }
      const restart = () => {
        if (closed) return
        clearTimeout(timer)
        clearTimeout(watchdog)
        es?.close()
        es = null
        attempt = 0
        connect()
      }
      const onVisible = () => {
        report()
        if (document.visibilityState === 'hidden') {
          hiddenAt = Date.now()
          clearTimeout(watchdog)
          return
        }
        const away = hiddenAt ? Date.now() - hiddenAt : 0
        hiddenAt = 0
        if (!es || es.readyState !== EventSource.OPEN || away > RESUME_MS) restart()
        else feed()
      }
      const onOnline = () => restart()
      const onPageShow = (e: PageTransitionEvent) => e.persisted && restart()

      const setState = (s: ConnectionState) => !closed && onState(s)

      const connect = () => {
        if (closed) return
        setState(attempt === 0 ? 'connecting' : 'reconnecting')
        es = new EventSource(`/api/events?cid=${device}${pcNudo ? '&pc=1' : ''}`, { withCredentials: true })
        es.addEventListener('open', () => {
          attempt = 0
          setState('live')
          if (pcNudo) onPcListo?.(device)
          feed()
        })
        es.addEventListener('ping', (ev) => {
          const build = parseData((ev as MessageEvent).data)?.build
          if (typeof build === 'string' && build) onBuild?.(build)
          if (seen() && Date.now() - lastReport > PRESENCE_RENEW_MS) report(true)
          feed()
        })
        es.addEventListener('build', (ev) => {
          const id = parseData((ev as MessageEvent).data)?.id
          if (typeof id === 'string' && id) onBuild?.(id)
          report()
        })
        es.addEventListener('board', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          if (data) onBoard(normalizeBoard(data))
          feed()
        })
        es.addEventListener('session', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          if (typeof data?.session_id === 'string') onSession?.({ session_id: data.session_id, mtime: String(data.mtime ?? '') })
        })
        es.addEventListener('biblioteca', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          const ids = Array.isArray(data?.nuevos) ? data.nuevos.filter((x: unknown) => typeof x === 'string') : []
          if (ids.length) onLibrary?.(ids)
        })
        es.addEventListener('aviso', (ev) => {
          const id = parseData((ev as MessageEvent).data)?.id
          if (Number.isInteger(id)) onAviso?.(id)
        })
        es.addEventListener('pedido_pestana', (ev) => {
          const e = normalizePedidoPestanaEvento(parseData((ev as MessageEvent).data))
          if (e) onPedidoPestana?.(e)
          feed()
        })
        es.addEventListener('nudo', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          if (data) onNudo?.(data, device)
          feed()
        })
        es.addEventListener('guia', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          if (data) onGuia?.(data, device)
          feed()
        })
        for (const nombre of EVENTOS_REUNION) {
          es.addEventListener(nombre, (ev) => {
            onReunion?.(nombre, parseData((ev as MessageEvent).data), device)
            feed()
          })
        }
        es.addEventListener('abrir_terminal', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          const pane_id = typeof data?.pane_id === 'string' ? data.pane_id : ''
          const titulo = typeof data?.titulo === 'string' ? data.titulo : ''
          if (pane_id && titulo) onAbrirTerminal?.({ pane_id, titulo })
          feed()
        })
        es.addEventListener('avisos_leidos', (ev) => {
          const raw = parseData((ev as MessageEvent).data)?.tags
          const tags = (Array.isArray(raw) ? raw : [])
            .filter((t: unknown) => typeof t === 'string' && AVISO_TAG_RE.test(t))
            .slice(0, 50)
          onAvisosLeidos?.(tags)
        })
        es.addEventListener('orden_tablero', (ev) => {
          const raw = parseData((ev as MessageEvent).data)?.orden
          const orden = Array.isArray(raw) ? raw.filter((x: unknown) => typeof x === 'string') : []
          onOrdenTablero?.(orden)
          feed()
        })
        es.addEventListener('orden_pestanas', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          const grupo = typeof data?.grupo === 'string' ? data.grupo : ''
          const orden = Array.isArray(data?.orden) ? data.orden.filter((x: unknown) => typeof x === 'string') : []
          onOrdenPestanas?.({ grupo, orden })
          feed()
        })
        es.addEventListener('programadas', () => {
          if (typeof window !== 'undefined') window.dispatchEvent(new Event(EVENTO_PROGRAMADAS))
          feed()
        })
        es.addEventListener('cursor', () => {
          if (typeof window !== 'undefined') window.dispatchEvent(new Event(EVENTO_CURSOR))
          feed()
        })
        es.addEventListener('plegadas', (ev) => {
          const raw = parseData((ev as MessageEvent).data)?.plegadas
          const plegadas = Array.isArray(raw) ? raw.filter((x: unknown) => typeof x === 'string') : []
          onPlegadas?.(plegadas)
          feed()
        })
        es.addEventListener('silenciadas', (ev) => {
          const raw = parseData((ev as MessageEvent).data)?.silenciadas
          onSilenciadas?.(Array.isArray(raw) ? raw.filter((x: unknown) => typeof x === 'string') : [])
          feed()
        })
        es.addEventListener('guardado', (ev) => {
          const g = normalizeGuardado(parseData((ev as MessageEvent).data))
          if (g) onGuardado?.(g)
        })
        es.addEventListener('mrs', (ev) => {
          const version = parseData((ev as MessageEvent).data)?.version
          if (Number.isInteger(version)) onMrs?.(version)
        })
        es.addEventListener('notas', (ev) => {
          const d = parseData((ev as MessageEvent).data)
          if (Number.isInteger(d?.version)) onNotas?.({ version: d.version, pendientes: Number.isInteger(d.pendientes) ? d.pendientes : 0 })
        })
        es.addEventListener('permisos', (ev) => {
          const data = parseData((ev as MessageEvent).data)
          const list = Array.isArray(data?.pedidos) ? data.pedidos : []
          const pedidos = list
            .map((p: unknown) => normalizeDialog({ tipo: 'pedido', pedido: p }))
            .filter((v: DialogView): v is { tipo: 'pedido'; pedido: PedidoPermiso } => v.tipo === 'pedido')
            .map((v: { tipo: 'pedido'; pedido: PedidoPermiso }) => v.pedido)
          onPermisos?.(pedidos)
        })
        es.addEventListener('error', () => {
          clearTimeout(watchdog)
          es?.close()
          es = null
          if (closed) return
          attempt++
          setState('reconnecting')
          const base = Math.min(30_000, 1000 * 2 ** Math.min(attempt - 1, 5))
          timer = setTimeout(async () => {
            // EventSource hides the status code: probe once so an expired cookie sends us to the PIN.
            try {
              await guard(request('/api/board'))
            } catch (e) {
              if (e instanceof ApiError && e.status === 401) return
            }
            connect()
          }, base * (0.75 + Math.random() * 0.5))
        })
      }

      document.addEventListener('visibilitychange', onVisible)
      window.addEventListener('online', onOnline)
      window.addEventListener('pageshow', onPageShow)
      window.addEventListener('focus', onFocusChange)
      window.addEventListener('blur', onFocusChange)
      window.addEventListener('pagehide', onPageHide)
      connect()
      return () => {
        closed = true
        reportNow = null
        clearTimeout(timer)
        clearTimeout(watchdog)
        document.removeEventListener('visibilitychange', onVisible)
        window.removeEventListener('online', onOnline)
        window.removeEventListener('pageshow', onPageShow)
        window.removeEventListener('focus', onFocusChange)
        window.removeEventListener('blur', onFocusChange)
        window.removeEventListener('pagehide', onPageHide)
        es?.close()
      }
    },

    getSubagentes: (sid) => guard(json(`/api/sessions/${encodeURIComponent(sid)}/subagentes`).then(normalizeSubagentes)),
    getDigest: (sid, turns = 8) =>
      guard(json(`/api/sessions/${encodeURIComponent(sid)}/digest?turns=${turns}`).then(normalizeDigest)),

    getTranscript(sid, before, limit = 60, desde) {
      const query = new URLSearchParams({ limit: String(limit) })
      if (before != null) query.set('before', String(before))
      if (desde != null) query.set('desde', String(desde))
      return guard(json(`/api/sessions/${encodeURIComponent(sid)}/transcript?${query}`).then(normalizeTranscript))
    },

    uploadFile: (file, onProgress, signal) => guard(tracked(uploadWithProgress(file, onProgress, signal))),

    getVozEstado: () => guard(json('/api/voz/estado').then(normalizeVozEstado)),

    transcribirVoz(audio, signal) {
      const form = new FormData()
      form.append('file', audio, `voz.${extFor(audio.type)}`)
      return guard(request('/api/voz/transcribir', { method: 'POST', body: form, signal }).then((r) => r.json()).then(normalizeVozResultado))
    },

    abrirEnPc: (paneId, titulo) =>
      guard(
        post('/api/abrir-en-pc', { pane_id: paneId, titulo })
          .then((r) => r.json())
          .then((d) => {
            if (d?.ok === true) return { ok: true as const }
            if (d?.ok === false && d?.motivo === 'sin_pc') return { ok: false as const, motivo: 'sin_pc' as const }
            throw new ApiError(0, 'Respuesta inválida')
          }),
      ),

    irAPc: (sid) =>
      guard(request(`/api/sesiones/${encodeURIComponent(sid)}/ir-a-pc`, { method: 'POST' }).then(() => undefined)),

    markSeen: (sid) => guard(post(`/api/sessions/${encodeURIComponent(sid)}/seen`).then(() => undefined)),

    marcarPreguntaVista: (sid) => guard(post(`/api/sessions/${encodeURIComponent(sid)}/pregunta-vista`).then(() => undefined)),

    getMemoriaEstado: () => guard(json('/api/memoria/estado').then(normalizeMemoriaEstado)),
    reindexarMemoria: () => guard(post('/api/memoria/reindexar').then(() => undefined)),
    borrarMemoria: () => guard(request('/api/memoria/indice', { method: 'DELETE' }).then(() => undefined)),
    getMemoriaCita: (ref) =>
      guard(json(ref.tipo === 'engram' ? `/api/memoria/cita?engram=${encodeURIComponent(ref.id)}` : `/api/memoria/cita?session_id=${encodeURIComponent(ref.session_id)}&turno=${ref.turno}`).then(normalizeMemoriaCita)),
    getLimpieza: (dias) => guard(json(`/api/limpieza/candidatos${dias ? `?dias=${Math.min(90, Math.max(1, Math.floor(dias)))}` : ''}`).then(normalizeLimpieza)),
    previewLimpieza: (items) => guard(post('/api/limpieza/preview', { items }).then((r) => r.json()).then(normalizeLimpiezaPreview)),
    ejecutarLimpieza: (body, h: LimpiezaHandlers, signal) => tracked((async () => {
      const res = await guard(request('/api/limpieza/ejecutar', { method: 'POST', body: JSON.stringify(body), headers: { Accept: 'text/event-stream' }, signal }))
      if (!res.body) throw new ApiError(0, 'Respuesta sin cuerpo')
      const parser = createSSEParser(({ event, data }) => {
        const d = parseData(data) ?? {}
        if (event === 'item') {
          h.onItem({
            target_id: str(d.target_id),
            ok: d.ok === true,
            error: str(d.error),
            sesiones: normalizeCloseResult({ sesiones: d.sesiones }).sesiones,
          })
        } else if (event === 'guardando') { const g = normalizeGuardado(d); if (g) h.onGuardando?.(g) }
        else if (event === 'fin') h.onFin({ cerrados: Number(d.cerrados) || 0, salteados: Number(d.salteados) || 0 })
      })
      const reader = res.body.pipeThrough(new TextDecoderStream()).getReader()
      for (;;) {
        const { value, done } = await reader.read()
        if (done) break
        parser.feed(value)
      }
      parser.end()
    })()),

    getClaudeUso: () => guard(json('/api/uso/claude').then(normalizeClaudeUso)),
    proponerVariante: (body) =>
      guard(
        post('/api/traspaso/variante', body)
          .then((r) => r.json())
          .then((r) => {
            const m = normalizeMessage(r?.message)
            if (!m) throw new ApiError(0, 'Respuesta inválida')
            return m
          }),
      ),

    async executeMensaje(body) {
      const d = await guard(post('/api/mensaje/execute', body).then((r) => r.json()))
      return { ok: d?.ok !== false, pane_id: String(d?.pane_id ?? ''), event: normalizeMessage(d?.event) }
    },

    stopSession: (paneId) => guard(post('/api/sessions/stop', { pane_id: paneId }).then(() => undefined)),

    previewClose: (tipo, targetId) =>
      guard(post('/api/close/preview', { tipo, target_id: targetId }).then((r) => r.json()).then(normalizeClosePreview)),

    executeClose: (body) => guard(post('/api/close/execute', body).then((r) => r.json()).then(normalizeCloseResult)),

    getDialog: (sid) => guard(json(`/api/sessions/${encodeURIComponent(sid)}/dialog`).then(normalizeDialog)),

    getPregunta: (sid) => guard(json(`/api/sessions/${encodeURIComponent(sid)}/pregunta`).then(normalizePregunta)),

    async responderPregunta(sid, body) {
      const d = await guard(post(`/api/sessions/${encodeURIComponent(sid)}/pregunta/responder`, body).then((r) => r.json()))
      return { ok: d?.ok !== false }
    },

    async correrComando(sid, body) {
      const d = await guard(post(`/api/sessions/${encodeURIComponent(sid)}/comando`, body).then((r) => r.json()))
      return { ok: d?.ok === true, comando: typeof d?.comando === 'string' ? d.comando : '' }
    },

    async answerDialog(body) {
      try {
        const d = await post('/api/sessions/dialog/answer', body).then((r) => r.json())
        return { ok: d?.ok === true, interrumpida: d?.interrumpida === true }
      } catch (e) {
        // A wrong PIN is also a 401, but the session is fine: only a real 401 sends the user to the login.
        if (e instanceof ApiError && e.status === 401 && e.detail !== PIN_WRONG) onUnauthorized()
        throw e
      }
    },

    async decidirPermiso(id, req) {
      try {
        const d = await post(`/api/permisos/${encodeURIComponent(id)}/decidir`, req).then((r) => r.json())
        const v = normalizeDialog({ tipo: 'pedido', pedido: d })
        if (v.tipo !== 'pedido') throw new ApiError(0, 'Respuesta inválida')
        return v.pedido
      } catch (e) {
        if (e instanceof ApiError && e.status === 401 && e.detail !== PIN_WRONG) onUnauthorized()
        throw e
      }
    },

    getPermisos: () =>
      guard(
        json('/api/permisos').then((d) => {
          const list = Array.isArray(d?.pedidos) ? d.pedidos : []
          const pedidos = list
            .map((p: unknown) => normalizeDialog({ tipo: 'pedido', pedido: p }))
            .filter((v: DialogView): v is { tipo: 'pedido'; pedido: PedidoPermiso } => v.tipo === 'pedido')
            .map((v: { tipo: 'pedido'; pedido: PedidoPermiso }) => v.pedido)
          return { pedidos }
        }),
      ),

    getPermisosRegistro: () => guard(json('/api/permisos/registro').then(normalizePermisosRegistro)),

    async getHandoff(name) {
      const d = await guard(json(`/api/handoffs/${encodeURIComponent(name)}`))
      return typeof d?.text === 'string' ? d.text : ''
    },

    revokeAll: () => guard(post('/api/sessions/revoke-all').then(() => undefined)),

    getLibrary: (filters, cursor, limit = 60) => guard(json(`/api/biblioteca?${libQuery(filters, cursor, limit)}`).then(normalizeLibListing)),

    async getLibraryItem(id, filters) {
      const query = filters ? libQuery(filters) : ''
      const item = normalizeLibItem(await guard(json(`/api/biblioteca/${encodeURIComponent(id)}${query ? `?${query}` : ''}`)))
      if (!item) throw new ApiError(404, 'No encontrado')
      return item
    },

    getLibrarySessions: () => guard(json('/api/biblioteca/sesiones').then(normalizeLibSessions)),

    async quitarLibrary(ids) {
      const d = await guard(post('/api/biblioteca/quitar', { ids }).then((r) => r.json()))
      return typeof d?.quitados === 'number' ? d.quitados : 0
    },

    async getLibraryText(id) {
      const d = await guard(json(`/api/biblioteca/${encodeURIComponent(id)}/texto`))
      return typeof d?.text === 'string' ? d.text : ''
    },

    async getLibraryCharla(id) {
      const d = await guard(json(`/api/biblioteca/${encodeURIComponent(id)}/charla`))
      if (typeof d?.charla !== 'string') throw new ApiError(502, 'Respuesta inválida')
      return d.charla
    },

    async getTerminalSalida(paneId, rev, signal) {
      const q = rev ? `?rev=${encodeURIComponent(rev)}` : ''
      return normalizeTerminalSalida(await guard(json(`/api/terminales/${encodeURIComponent(paneId)}/salida${q}`, { signal })))
    },

    async getTerminalConfig() {
      return normalizeTerminalConfig(await guard(json('/api/terminales/config')))
    },
    async getTerminalesCarpetas() {
      const d = await guard(json('/api/terminales/carpetas'))
      const carpetas = Array.isArray(d?.carpetas) ? d.carpetas : []
      const gruposRaw = Array.isArray(d?.grupos) ? d.grupos : []
      const grupoOk = (g: unknown): g is { id: string; nombre: string; carpeta: string | null } => {
        if (!g || typeof g !== 'object') return false
        const o = g as { id?: unknown; nombre?: unknown; carpeta?: unknown }
        return (
          typeof o.id === 'string' &&
          /^g\d{1,6}$/.test(o.id) &&
          typeof o.nombre === 'string' &&
          (o.carpeta === null || typeof o.carpeta === 'string')
        )
      }
      return {
        carpetas: carpetas
          .filter((c: unknown): c is { ruta: string; nombre: string; repo?: unknown } => !!c && typeof c === 'object' && typeof (c as { ruta?: unknown }).ruta === 'string' && typeof (c as { nombre?: unknown }).nombre === 'string')
          .map((c: { ruta: string; nombre: string; repo?: unknown }) => ({ ruta: c.ruta, nombre: c.nombre, repo: c.repo === true })),
        grupos: gruposRaw.filter(grupoOk).map((g: { id: string; nombre: string; carpeta: string | null }) => ({
          id: g.id,
          nombre: g.nombre,
          carpeta: g.carpeta,
        })),
      }
    },
    async postTerminalesNuevaTarea(body) {
      const d = await guard(post('/api/terminales/nueva-tarea', body).then((r) => r.json()))
      if (!d?.ok || typeof d.pane_id !== 'string' || typeof d.ruta !== 'string' || typeof d.rama !== 'string') throw new ApiError(502, 'Respuesta rara del servidor')
      return { ok: true as const, pane_id: d.pane_id, ruta: d.ruta, rama: d.rama, ...(d.pegado === false ? { pegado: false as const } : {}), ...(normalizarPreparar(d.preparar) ? { preparar: normalizarPreparar(d.preparar) } : {}) }
    },
    async postTerminalesNuevaTareaConfiar(body) {
      const d = await guard(post('/api/terminales/nueva-tarea/confiar', body).then((r) => r.json()))
      if (!d?.ok) throw new ApiError(502, 'Respuesta rara del servidor')
      return { ok: true as const }
    },
    async postBorrarCopia(ruta) {
      const d = await guard(post('/api/terminales/nueva-tarea/borrar-copia', { ruta }).then((r) => r.json()))
      if (!d?.ok) throw new ApiError(502, 'Respuesta rara del servidor')
      return { ok: true as const }
    },
    async postTerminalesNueva(body) {
      const d = await guard(post('/api/terminales/nueva', body).then((r) => r.json()))
      if (!d?.ok || typeof d.espacio_id !== 'string' || typeof d.sesion_id !== 'string') throw new ApiError(502, 'Respuesta rara del servidor')
      return { ok: true as const, espacio_id: d.espacio_id, sesion_id: d.sesion_id }
    },
    async getSesionesViejas(qs = '') {
      const d = await guard(json(`/api/sesiones/viejas${qs || ''}`))
      return Array.isArray(d) ? d : []
    },
    async postSesionesViejasRetomar(body) {
      const d = await guard(post('/api/sesiones/viejas/retomar', body).then((r) => r.json()))
      if (!d?.ok || typeof d.sesion_id !== 'string') throw new ApiError(502, 'Respuesta rara del servidor')
      return {
        ok: true as const,
        espacio_id: String(d.espacio_id ?? ''),
        sesion_id: d.sesion_id,
        pane_id: typeof d.pane_id === 'string' ? d.pane_id : d.sesion_id,
      }
    },
    async previewTerminal(paneId) {
      return normalizeTerminalPreview(await guard(json('/api/terminales/preview', { method: 'POST', body: JSON.stringify({ pane_id: paneId }) })))
    },
    async terminalCtrlC(body) {
      await guard(post('/api/terminales/ctrl-c', body))
    },
    async cerrarTerminal(body) {
      await guard(post('/api/terminales/cerrar', body))
    },
    async renombrarTerminal(body) {
      await guard(post('/api/terminales/renombrar', body))
    },
    listarNotas: () => guard(json('/api/notas')),
    crearNota: (b) => guard(post('/api/notas', b).then((r) => r.json())),
    editarNota: (id, b) =>
      guard(request(`/api/notas/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(b) }).then((r) => r.json())),
    async borrarNota(id) {
      await guard(request(`/api/notas/${encodeURIComponent(id)}`, { method: 'DELETE' }))
    },
    async repetirPreparar(body) {
      return normalizeRepetirPrep(await guard(post('/api/terminales/repetir/preparar', body).then((r) => r.json())))
    },
    async repetirConfirmar(body) {
      const d = await guard(post('/api/terminales/repetir/confirmar', body).then((r) => r.json()))
      return d?.ejecutado === true
    },
    async abrirVentana(pin) {
      try {
        const d = await post('/api/terminales/ventana', { pin }).then((r) => r.json())
        return { token: str(d?.token), vence_en: Number(d?.vence_en) || 0, inactividad: Number(d?.inactividad) || 0 }
      } catch (e) {
        if (e instanceof ApiError && e.status === 401 && e.detail !== PIN_WRONG) onUnauthorized()
        throw e
      }
    },
    async cerrarVentana(token, keepalive = false) {
      await request('/api/terminales/ventana/cerrar', { method: 'POST', body: '{}', keepalive, headers: { 'X-Orq-Escritura': token } })
    },
    async enviarComando(body, token) {
      await guard(request('/api/terminales/comando', { method: 'POST', body: JSON.stringify(body), headers: { 'X-Orq-Escritura': token } }))
    },
    async getTerminalAuditoria(limit) {
      return normalizeTerminalAuditoria(await guard(json(`/api/terminales/auditoria?limit=${Math.min(Math.max(limit | 0, 1), 50)}`)))
    },
  }
}
