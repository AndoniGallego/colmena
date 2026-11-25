import type { CopiaCierre, Agent, AgentCtx, CtxCompact, CloseBlocker, ClosePane, ClosePreview, CloseResult, Guardado, GuardadoPane, GuardadoTarget, CloseSession, AgentStatus, CtxLevel, StatusLine, Board, ChatMessage, Digest, DigestTurn, Subagente, SubagenteEstado, TranscriptItem, TranscriptPage, Upload, VozEstado, VozResultado, LibItem, LibKind, LibListing, LibSession, Terminal, TerminalEstado, TerminalSalida, TerminalConfig, TerminalPreview, RepetirPrep, TerminalAuditoria, LimpiezaCandidatos, LimpiezaItem, LimpiezaPreviewItem, LimpiezaRazon, Aviso, AvisoKindBase, AvisosPage, MemoriaCita, MemoriaEstado, PasoMemoria, ReporteFila, PedidoPestana, PedidoPestanaEstado, PedidoPestanaTab, PedidoPestanaCierre, ObjetivoCierre, VistaCierrePedido } from './types'
import { toEstado } from '../lib/estado'
import { normalizeTraba } from '../lib/trabas'
import { MAX_FILES, isUploadId } from '../lib/attachments'

const STATUSES: AgentStatus[] = ['idle', 'working', 'blocked', 'done', 'unknown']

export function asStatus(v: unknown): AgentStatus {
  return STATUSES.includes(v as AgentStatus) ? (v as AgentStatus) : 'unknown'
}

const str = (v: unknown, fallback = ''): string => (typeof v === 'string' ? v : fallback)

let seq = 0
export const localId = (prefix: string) => `${prefix}-${Date.now().toString(36)}-${(seq++).toString(36)}`

const ESTADOS: TerminalEstado[] = ['prompt', 'corriendo', 'desconocido']

export function normalizeTerminales(raw: any): Terminal[] {
  return (Array.isArray(raw) ? raw : [])
    .filter((x: any) => x && typeof x.pane_id === 'string' && x.pane_id)
    .map((x: any) => ({
      pane_id: x.pane_id,
      terminal_id: str(x.terminal_id),
      titulo: str(x.titulo),
      cwd: str(x.cwd),
      proceso: str(x.proceso),
      estado: ESTADOS.includes(x.estado) ? x.estado : 'desconocido',
      protegida: x.protegida === true,
    }))
}

const MOTIVOS = ['protegido', 'apagada', 'ocupada', 'desconocido']

export function normalizeTerminalSalida(raw: any): TerminalSalida {
  return {
    sin_cambios: raw?.sin_cambios === true,
    revision: str(raw?.revision),
    ansi: str(raw?.ansi),
    truncado: raw?.truncado === true,
    cwd: str(raw?.cwd),
    proceso: str(raw?.proceso),
    estado: ESTADOS.includes(raw?.estado) ? raw.estado : 'desconocido',
    puede_escribir: raw?.puede_escribir === true,
    motivo: MOTIVOS.includes(raw?.motivo) ? raw.motivo : null,
  }
}

export function normalizeTerminalConfig(raw: any): TerminalConfig {
  const v = raw?.ventana ?? {}
  return {
    escritura: raw?.escritura === true,
    vivo: raw?.vivo === true,
    comandos_rapidos: (Array.isArray(raw?.comandos_rapidos) ? raw.comandos_rapidos : []).filter((c: unknown) => typeof c === 'string').slice(0, 12),
    ventana: { abierta: v.abierta === true, vence_en: Number(v.vence_en) || 0, inactividad_en: Number(v.inactividad_en) || 0 },
  }
}

export function normalizeTerminalPreview(raw: any): TerminalPreview {
  return {
    huella: str(raw?.huella),
    pane_id: str(raw?.pane_id),
    workspace: str(raw?.workspace),
    tab: str(raw?.tab),
    titulo: str(raw?.titulo),
    cwd: str(raw?.cwd),
    proceso: str(raw?.proceso),
    estado: ESTADOS.includes(raw?.estado) ? raw.estado : 'desconocido',
    protegida: raw?.protegida === true,
    puede_escribir: raw?.puede_escribir === true,
    // Sin el dato se supone lo peor: así cerrar siempre pide confirmación.
    cierra: raw?.cierra === 'terminal' || raw?.cierra === 'espacio' ? raw.cierra : 'pestana',
  }
}

export function normalizeRepetirPrep(raw: any): RepetirPrep {
  return { linea: typeof raw?.linea === 'string' && raw.linea ? raw.linea : null, antes: str(raw?.antes), huella2: str(raw?.huella2) }
}

export function normalizeTerminalAuditoria(raw: any): TerminalAuditoria[] {
  return (Array.isArray(raw?.entradas) ? raw.entradas : []).slice(0, 50).map((e: any) => ({
    ts: str(e?.ts),
    accion: str(e?.accion),
    dispositivo: str(e?.dispositivo),
    workspace: str(e?.workspace),
    proceso: str(e?.proceso),
    comando: str(e?.comando),
    ok: e?.ok === true,
    error: str(e?.error),
  }))
}

const natural = (v: unknown): number | null => (typeof v === 'number' && Number.isInteger(v) && v >= 0 ? v : null)

function normalizeCompact(raw: any): CtxCompact | null {
  const pre = natural(raw?.pre)
  const post = natural(raw?.post)
  if (pre === null || post === null) return null
  return { ts: str(raw?.ts), trigger: raw?.trigger === 'manual' ? 'manual' : 'auto', pre, post }
}

export function normalizeCtx(raw: any): AgentCtx | null {
  const pct = natural(raw?.pct)
  const tokens = natural(raw?.tokens)
  const window = natural(raw?.window)
  if (pct === null || !tokens || !window || (raw?.fuente !== 'statusline' && raw?.fuente !== 'transcript')) return null
  const last = normalizeCompact(raw?.ultima_compactacion)
  return {
    pct: Math.min(pct, 999),
    tokens,
    window,
    fuente: raw.fuente,
    compactaciones: natural(raw?.compactaciones) ?? 0,
    ultima_compactacion: last,
  }
}

const FONDO_TIPOS = new Set(['cursor', 'agente', 'comando', 'workflow'])

function normalizeFondo(raw: unknown): Agent['fondo'] {
  if (!Array.isArray(raw)) return []
  const out: NonNullable<Agent['fondo']> = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const o = item as Record<string, unknown>
    const tipo = str(o.tipo)
    const id = str(o.id)
    const texto = str(o.texto)
    if (!FONDO_TIPOS.has(tipo) || !id || !texto) continue
    const desde = Number(o.desde)
    out.push({ id, tipo: tipo as NonNullable<Agent['fondo']>[number]['tipo'], texto: texto.slice(0, 60), desde: Number.isFinite(desde) ? desde : 0 })
  }
  return out
}

function normalizeAgent(a: any): Agent {
  return {
    pane_id: str(a?.pane_id),
    kind: str(a?.kind, 'claude'),
    status: asStatus(a?.status),
    session_id: a?.session_id ? String(a.session_id) : null,
    title: str(a?.title),
    doing: str(a?.doing),
    pending: str(a?.pending),
    estado: toEstado(a?.estado),
    asks_user: Boolean(a?.asks_user),
    pendiente: Boolean(a?.pendiente),
    preguntas: typeof a?.preguntas === 'number' && a.preguntas > 0 ? Math.floor(a.preguntas) : 0,
    unread: Boolean(a?.unread),
    last_activity: a?.last_activity ? String(a.last_activity) : null,
    fondo: normalizeFondo(a?.fondo),
    traba: normalizeTraba(a?.traba),
    ctx: normalizeCtx(a?.ctx),
    uso: normalizeUsoHoy(a?.uso),
  }
}

function normalizeUsoHoy(raw: any): Agent['uso'] {
  const total = raw?.total
  if (typeof total !== 'number' || !Number.isFinite(total) || total < 0) return null
  const usd = raw?.usd
  return { total, usd: typeof usd === 'number' && Number.isFinite(usd) && usd >= 0 ? usd : null }
}

const stringList20 = (raw: unknown) => (Array.isArray(raw) ? raw.filter((x: unknown) => typeof x === 'string').slice(0, 20) : [])

export function normalizeBoard(raw: any): Board {
  const conflictos = stringList20(raw?.conflictos)
  const caidos = stringList20(raw?.caidos)
  return {
    updated_at: str(raw?.updated_at, new Date().toISOString()),
    focused_tab_id: raw?.focused_tab_id ?? null,
    self_pane_id: raw?.self_pane_id ?? null,
    terminales: raw?.terminales === 'sin_conexion' ? 'sin_conexion' : 'ok',
    conflictos,
    caidos,
    workspaces: (Array.isArray(raw?.workspaces) ? raw.workspaces : []).map((w: any) => ({
      id: str(w?.id),
      number: Number(w?.number) || 0,
      label: str(w?.label),
      pinned: w?.pinned === true,
      status: asStatus(w?.status),
      tabs: (Array.isArray(w?.tabs) ? w.tabs : []).map((t: any) => ({
        id: str(t?.id),
        label: str(t?.label),
        terminales: normalizeTerminales(t?.terminales),
        agents: (Array.isArray(t?.agents) ? t.agents : []).map(normalizeAgent),
      })),
    })),
  }
}

export function normalizeMessage(raw: any): ChatMessage | null {
  if (!raw || typeof raw !== 'object') return null
  const role = String(raw.role ?? '').toLowerCase()
  // The server's automatic turn after a consultation is not something the user wrote.
  if (role === 'user' && raw.origen === 'consulta') {
    return { id: raw.id ? String(raw.id) : localId('m'), role: 'event', text: 'Llegaron las respuestas de las sesiones', ts: raw.ts ?? undefined }
  }
  const text = str(raw.text, str(raw.content))
  return {
    id: raw.id ? String(raw.id) : localId('m'),
    role: role === 'user' ? 'user' : role === 'event' ? 'event' : role === 'reporte' ? 'reporte' : 'assistant',
    text,
    ts: raw.ts ?? raw.created_at ?? undefined,
    ...(role === 'assistant' && raw.origen === 'vigia'
      ? { origen: 'vigia' as const, ...(raw.aviso === true ? { aviso: true } : {}), ...(raw.visto === true ? { visto: true } : {}) }
      : {}),
    ...(role === 'event' && raw.kind === 'nueva' ? { kind: 'nueva' as const } : {}),
    ...(role === 'event' && raw.kind === 'respuesta' ? { kind: 'respuesta' as const, session_id: str(raw.session_id) } : {}),
    ...(role === 'reporte' ? reporteDe(raw) : {}),
    ...(role === 'assistant' && Array.isArray(raw.pasos) && raw.pasos.length ? { pasos: normalizePasos(raw.pasos) } : {}),
    ...(role === 'user' ? adjuntosDe(raw.adjuntos) : {}),
  }
}

const MAX_FILAS = 8

function reporteDe(raw: any): { items: ReporteFila[]; mas: number } {
  const list = Array.isArray(raw.items) ? raw.items : []
  const items = list
    .filter((r: any) => r && typeof r.session_id === 'string' && r.session_id)
    .slice(0, MAX_FILAS)
    .map((r: any) => ({
      session_id: r.session_id,
      pane_id: str(r.pane_id),
      nombre: str(r.nombre) || 'Sesión',
      donde: str(r.donde),
      pedido: str(r.pedido),
      quedo: str(r.quedo),
      pregunta: str(r.pregunta),
      cadena: r.cadena === true,
      plan_id: str(r.plan_id),
      fin: str(r.fin),
    }))
  const mas = typeof raw.mas === 'number' && Number.isFinite(raw.mas) && raw.mas > 0 ? Math.floor(raw.mas) : 0
  return { items, mas }
}

function adjuntosDe(raw: unknown): { adjuntos?: string[] } {
  const ids = Array.isArray(raw) ? raw.filter((id): id is string => typeof id === 'string' && isUploadId(id)).slice(0, MAX_FILES) : []
  return ids.length ? { adjuntos: ids } : {}
}

const normalizePasos = (list: any[]): PasoMemoria[] =>
  list.filter((p) => p && typeof p.name === 'string').slice(0, 20).map((p) => ({ name: p.name, summary: str(p.summary) }))

export function normalizeMemoriaEstado(raw: any): MemoriaEstado {
  const n = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? v : 0)
  const engram = raw?.engram === 'ok' || raw?.engram === 'deshabilitado' ? raw.engram : 'caido'
  return {
    habilitada: raw?.habilitada === true,
    indexados: Math.floor(n(raw?.indexados)),
    turnos: Math.floor(n(raw?.turnos)),
    tamano_mb: n(raw?.tamano_mb),
    ultima_actualizacion: typeof raw?.ultima_actualizacion === 'string' ? raw.ultima_actualizacion : null,
    actualizando: raw?.actualizando === true,
    engram,
  }
}

export function normalizeMemoriaCita(raw: any): MemoriaCita {
  if (raw?.tipo === 'engram') return { tipo: 'engram', id: Number(raw.id) || 0, texto: str(raw.texto) }
  return { tipo: 'sesion', session_id: str(raw?.session_id), turno: Number(raw?.turno) || 0, titulo: str(raw?.titulo), fecha: str(raw?.fecha), rol: str(raw?.rol), texto: str(raw?.texto) }
}

export function normalizeDigest(raw: any): Digest {
  const turns: DigestTurn[] = (Array.isArray(raw?.turns) ? raw.turns : []).map((t: any) => ({
    role: String(t?.role ?? '').toLowerCase() === 'user' ? 'user' : 'claude',
    text: str(t?.text),
  }))
  return { title: str(raw?.title), last_prompt: str(raw?.last_prompt), turns }
}

const KINDS = ['user', 'claude', 'tool', 'compact', 'imagenes']

const LEVELS: CtxLevel[] = ['ok', 'caution', 'warn']

export function normalizeStatusLine(raw: any): StatusLine {
  const pct = Number(raw?.ctx_pct)
  const known = raw?.ctx_pct != null && Number.isFinite(pct)
  return {
    model: str(raw?.model),
    ticket: str(raw?.ticket),
    ctx_pct: known ? Math.max(0, Math.round(pct)) : null,
    ctx_level: known && LEVELS.includes(raw?.ctx_level) ? raw.ctx_level : 'unknown',
    vpn: raw?.vpn === 'up' || raw?.vpn === 'down' ? raw.vpn : null,
  }
}

export function normalizeTranscript(raw: any): TranscriptPage {
  const items: TranscriptItem[] = (Array.isArray(raw?.items) ? raw.items : [])
    .filter((i: any) => KINDS.includes(i?.kind))
    .map((i: any) => {
      const lib = Array.isArray(i.lib_ids) ? i.lib_ids.filter((x: unknown) => typeof x === 'string') : []
      const compact = i.kind === 'compact' ? normalizeCompact(i.compact) : null
      const fotos = i.kind === 'imagenes' && Array.isArray(i.fotos)
        ? i.fotos.filter((f: unknown) => typeof (f as { id?: string })?.id === 'string').map((f: { id: string }) => ({ id: f.id }))
        : []
      return {
        kind: i.kind,
        text: str(i.text),
        name: str(i.name),
        summary: str(i.summary),
        ts: str(i.ts),
        ...(compact ? { compact: { trigger: compact.trigger, pre: compact.pre, post: compact.post } } : {}),
        ...(lib.length ? { lib_ids: lib } : {}),
        ...(fotos.length ? { fotos } : {}),
        ...(i.kind === 'claude' && typeof i.cmid === 'string' && i.cmid && Number.isInteger(i.cstart) && i.cstart >= 0
          ? { cmid: i.cmid, cstart: i.cstart }
          : {}),
        ...(i.kind === 'claude' && typeof i.ccwd === 'string' && i.ccwd.startsWith('/') && i.ccwd.length <= 500
          ? { ccwd: i.ccwd }
          : {}),
      }
    })
  return {
    items,
    before: Number.isInteger(raw?.before) ? raw.before : null,
    title: str(raw?.title),
    status: asStatus(raw?.status),
    pane_id: str(raw?.pane_id),
    status_line: normalizeStatusLine(raw?.status_line),
  }
}

export function normalizeUpload(raw: any): Upload {
  const kind = raw?.kind === 'image' || raw?.kind === 'pdf' ? raw.kind : 'text'
  return { id: str(raw?.id), name: str(raw?.name), size: Number(raw?.size) || 0, kind }
}

export function normalizeVozEstado(raw: any): VozEstado {
  return {
    habilitada: raw?.habilitada === true,
    modelo: str(raw?.modelo),
    cargado: raw?.cargado === true,
    ocupada: raw?.ocupada === true,
    max_segundos: Number(raw?.max_segundos) || 120,
  }
}

export function normalizeVozResultado(raw: any): VozResultado {
  return { texto: str(raw?.texto), duracion: Number(raw?.duracion) || 0, proceso: Number(raw?.proceso) || 0 }
}

const status = asStatus
const strOrNull = (v: unknown) => (typeof v === 'string' && v ? v : null)

export function normalizeBlockers(raw: any): CloseBlocker[] {
  return (Array.isArray(raw) ? raw : [])
    .filter((b: any) => typeof b?.pane_id === 'string')
    .map((b: any) => ({ pane_id: b.pane_id, status: status(b.status) }))
}

export function normalizeClosePreview(raw: any): ClosePreview {
  const panes: ClosePane[] = (Array.isArray(raw?.panes) ? raw.panes : []).map((p: any) => ({
    pane_id: str(p?.pane_id),
    kind: strOrNull(p?.kind),
    status: p?.kind ? status(p?.status) : null,
    titulo: str(p?.titulo),
    session_id: strOrNull(p?.session_id),
    cwd: str(p?.cwd),
    proceso: strOrNull(p?.proceso),
  }))
  return {
    tipo: raw?.tipo === 'workspace' ? 'workspace' : 'tab',
    target_id: str(raw?.target_id),
    label: str(raw?.label),
    workspace_label: str(raw?.workspace_label),
    cierra_workspace: raw?.cierra_workspace === true,
    tab_count: Number.isInteger(raw?.tab_count) && raw.tab_count > 0 ? raw.tab_count : 1,
    panes,
    bloqueantes: normalizeBlockers(raw?.bloqueantes),
    huella: str(raw?.huella),
  }
}

const nat0 = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0)

function normalizeRazon(r: any): LimpiezaRazon | null {
  if (r?.tipo === 'quieto' || r?.tipo === 'sin_claude') return { tipo: r.tipo, dias: nat0(r.dias) }
  if (r?.tipo === 'mergeada') return { tipo: 'mergeada', rama: str(r.rama), base: str(r.base) }
  return null
}

export function normalizeLimpieza(raw: any): LimpiezaCandidatos {
  const items: LimpiezaItem[] = []
  for (const i of Array.isArray(raw?.items) ? raw.items : []) {
    const target_id = str(i?.target_id)
    if (!target_id || (i?.tipo !== 'tab' && i?.tipo !== 'workspace')) continue
    const bloqueado = i?.bloqueado === 'corriendo' || i?.bloqueado === 'sin_leer' ? i.bloqueado : null
    items.push({
      tipo: i.tipo,
      target_id,
      workspace: str(i.workspace),
      label: str(i.label),
      razones: (Array.isArray(i.razones) ? i.razones : []).map(normalizeRazon).filter((x: LimpiezaRazon | null): x is LimpiezaRazon => !!x),
      sesiones: (Array.isArray(i.sesiones) ? i.sesiones : [])
        .filter((x: any) => typeof x?.session_id === 'string')
        .map((x: any) => ({ session_id: x.session_id, titulo: str(x.titulo), ultima: strOrNull(x.ultima), pendiente: str(x.pendiente) })),
      terminales: nat0(i.terminales),
      marcado: i.marcado === true && !bloqueado,
      bloqueado,
    })
  }
  const dias = nat0(raw?.dias)
  return { dias: dias || 7, items, generado_at: str(raw?.generado_at), git: raw?.git === 'parcial' || raw?.git === 'sin_datos' ? raw.git : 'ok' }
}

export function normalizeLimpiezaPreview(raw: any): LimpiezaPreviewItem[] {
  return (Array.isArray(raw) ? raw : [])
    .filter((x: any) => typeof x?.target_id === 'string' && (x?.tipo === 'tab' || x?.tipo === 'workspace'))
    .map((x: any) => ({
      tipo: x.tipo,
      target_id: x.target_id,
      preview: x.preview ? normalizeClosePreview(x.preview) : null,
      error: str(x.error),
      bloqueantes: normalizeBlockers(x.bloqueantes),
    }))
}

const PANE_ESTADOS = ['guardando', 'listo', 'bloqueado', 'fallo']
const TARGET_ESTADOS = ['guardando', 'cerrando', 'cerrado', 'error', 'cancelado']

export function normalizeGuardado(raw: any): Guardado | null {
  if (!raw || typeof raw.id !== 'string' || !Array.isArray(raw.targets)) return null
  return {
    id: raw.id,
    origen: str(raw.origen),
    plan_id: str(raw.plan_id),
    vencido: raw.vencido === true,
    puede_cerrar_igual: raw.puede_cerrar_igual === true,
    terminado: raw.terminado === true,
    targets: raw.targets.map((t: any) => ({
      key: str(t?.key),
      tipo: str(t?.tipo),
      target_id: str(t?.target_id),
      label: str(t?.label),
      estado: (TARGET_ESTADOS.includes(t?.estado) ? t.estado : 'guardando') as GuardadoTarget['estado'],
      error: str(t?.error),
      guardado: str(t?.guardado),
      sesiones: normalizeCloseResult({ sesiones: t?.resultado?.sesiones }).sesiones,
      copias: normalizeCopias(t?.resultado?.copias),
      panes: (Array.isArray(t?.panes) ? t.panes : []).map((p: any) => ({
        pane_id: str(p?.pane_id),
        titulo: str(p?.titulo),
        estado: (PANE_ESTADOS.includes(p?.estado) ? p.estado : 'guardando') as GuardadoPane['estado'],
      })),
    })),
  }
}

export function normalizeCopias(raw: any): CopiaCierre[] {
  return (Array.isArray(raw) ? raw : [])
    .filter((c: any) => typeof c?.ruta === 'string' && c.ruta)
    .map((c: any) => ({ ruta: c.ruta as string, rama: str(c.rama), borrable: c.borrable === true, motivo: str(c.motivo) }))
}

export function normalizeCloseResult(raw: any): CloseResult {
  const sesiones: CloseSession[] = (Array.isArray(raw?.sesiones) ? raw.sesiones : []).map((x: any) => ({
    session_id: strOrNull(x?.session_id),
    cwd: str(x?.cwd),
    titulo: str(x?.titulo),
  }))
  const aviso = str(raw?.aviso)
  const guardando = normalizeGuardado(raw?.guardando)
  const copias = normalizeCopias(raw?.copias)
  return { ok: raw?.ok !== false, sesiones, event: normalizeMessage(raw?.event), ...(aviso ? { aviso } : {}), ...(guardando ? { guardando } : {}), ...(copias.length ? { copias } : {}) }
}

const LIB_KINDS: LibKind[] = ['html', 'image', 'svg', 'gif', 'pdf', 'video', 'text', 'diagrama', 'pruebas', 'reunion', 'remoto', 'otro']

const VIEWER_SRC = /^https:\/\/[^/?#\s]+\/v\/[0-9a-f]{32}\/\d{9,12}\/[A-Za-z0-9_-]{43}\/$/

/** El visor vive en otro origen https bajo /v/: cualquier otra cosa no se embebe ni se abre. */
const viewerSrc = (v: unknown): string => (typeof v === 'string' && VIEWER_SRC.test(v) ? v : '')

export function normalizeLibItem(raw: any): LibItem | null {
  if (typeof raw?.id !== 'string' || !LIB_KINDS.includes(raw?.kind)) return null
  const vecinos = raw.vecinos
    ? { anterior: strOrNull(raw.vecinos.anterior), siguiente: strOrNull(raw.vecinos.siguiente) }
    : undefined
  return {
    id: raw.id,
    kind: raw.kind,
    source: str(raw.source),
    session_id: str(raw.session_id),
    session_titulo: str(raw.session_titulo),
    project: str(raw.project),
    subagent: str(raw.subagent),
    ts: str(raw.ts),
    title: str(raw.title),
    description: str(raw.description),
    caption: str(raw.caption),
    nombre: str(raw.nombre),
    donde: str(raw.donde),
    exists: raw.exists === true,
    copia: raw.copia === true,
    servible: raw.servible === true,
    motivo: str(raw.motivo),
    size: Number(raw.size) || 0,
    mime: str(raw.mime),
    url: str(raw.url),
    version: Number(raw.version) || 0,
    versions: (Array.isArray(raw.versions) ? raw.versions : []).map((v: any) => ({ version: Number(v?.version) || 0, ts: str(v?.ts) })),
    diagrama_raw: str(raw.diagrama_raw),
    pruebas_raw: str(raw.pruebas_raw),
    ...(raw.kind === 'reunion' ? { reunion_raw: strOrNull(raw.reunion_raw), tiene_charla: raw.tiene_charla === true } : {}),
    evidencias: Object.fromEntries(Object.entries(raw.evidencias && typeof raw.evidencias === 'object' ? raw.evidencias : {}).filter((e): e is [string, string] => typeof e[1] === 'string')),
    src: viewerSrc(raw.src),
    ...(vecinos ? { vecinos } : {}),
  }
}

export function normalizeLibListing(raw: any): LibListing {
  return {
    items: (Array.isArray(raw?.items) ? raw.items : []).map(normalizeLibItem).filter((i: LibItem | null): i is LibItem => !!i),
    cursor: strOrNull(raw?.cursor),
    indexando: raw?.indexando === true,
    total: Number(raw?.total) || 0,
  }
}

export function normalizeLibSessions(raw: any): LibSession[] {
  return (Array.isArray(raw) ? raw : [])
    .filter((s: any) => typeof s?.session_id === 'string')
    .map((s: any) => ({ session_id: s.session_id, titulo: str(s.titulo), proyecto: str(s.proyecto), n: Number(s.n) || 0, ultimo_ts: str(s.ultimo_ts) }))
}

const AVISO_KINDS: readonly string[] = ['asks', 'blocked', 'done', 'terminal', 'cierre', 'encadenar', 'vigia', 'mr', 'entorno', 'test', 'progreso', 'pestana', 'trabada'] satisfies AvisoKindBase[]
export const AVISO_TAG_RE = /^[A-Za-z0-9_.:-]{1,120}$/
export const PEDIDO_PESTANA_ID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i

const PEDIDO_ESTADOS: PedidoPestanaEstado[] = ['pendiente', 'abierto', 'rechazado', 'vencido', 'descartado']

/** `kindsExtra`: kinds de las piezas montadas, que también se aceptan. */
export function normalizeAvisos(raw: any, incluirPrueba = false, kindsExtra: readonly string[] = []): AvisosPage {
  const list: any[] = Array.isArray(raw?.items) ? raw.items : []
  const items: Aviso[] = list
    .filter((a) => a && Number.isInteger(a.id) && a.id > 0 && Number.isFinite(a.ts) && (AVISO_KINDS.includes(a.kind) || kindsExtra.includes(a.kind)))
    .filter((a) => incluirPrueba || !a.prueba)
    .map((a) => ({
      id: a.id,
      ts: a.ts,
      kind: a.kind,
      titulo: str(a.titulo).slice(0, 200),
      cuerpo: str(a.cuerpo).slice(0, 400),
      session_id: str(a.session_id),
      pane_id: str(a.pane_id),
      fecha: str(a.fecha),
      mr: /^\d{1,12}:\d{1,9}$/.test(str(a.mr)) ? str(a.mr) : '',
      mensaje: /^[0-9a-f]{32}$/.test(str(a.mensaje)) ? str(a.mensaje) : '',
      ...(PEDIDO_PESTANA_ID_RE.test(str(a.pedido)) ? { pedido: str(a.pedido) } : {}),
      entregado: a.entregado === true,
      leido: a.leido === true,
      motivo: str(a.motivo).slice(0, 40),
      tag: AVISO_TAG_RE.test(str(a.tag)) ? str(a.tag) : '',
      prueba: a.prueba === true,
    }))
  const n = Number(raw?.no_leidos)
  const l = Number(raw?.leidos_hasta)
  return { items, hayMas: raw?.hay_mas === true, noLeidos: Number.isInteger(n) && n > 0 ? n : 0, leidosHasta: Number.isInteger(l) && l > 0 ? l : 0 }
}

/** Igual que MODELO_CURSOR_RE del backend, sin "-" inicial (no puede parecer un flag). */
const MODELO_CURSOR_RE = /^[A-Za-z0-9._\-[\]=,]{1,80}$/

/** Pedido de trabajador Cursor: sin pestañas, terminal ni tarjeta; un modelo inválido descarta el pedido. */
function pedidoCursor(out: PedidoPestana, p: any): PedidoPestana | null {
  if (!out.mensaje.trim() || !out.nombre?.trim() || !out.carpeta.trim()) return null
  const modelo = p.cursor?.modelo
  const cursor: { modelo?: string } = {}
  if (modelo !== undefined && modelo !== null && modelo !== '') {
    if (typeof modelo !== 'string' || !MODELO_CURSOR_RE.test(modelo) || modelo.startsWith('-')) return null
    cursor.modelo = modelo
  }
  const { pestanas: _p, tarjeta: _t, terminal: _x, ...resto } = out
  return { ...resto, accion: 'cursor', cursor }
}

const OBJETIVOS_CIERRE: ObjetivoCierre[] = ['sesion', 'pestana', 'tarjeta']

const contador = (v: unknown) => {
  const n = Number(v)
  return Number.isFinite(n) ? Math.max(0, Math.trunc(n)) : 0
}

function pedidoCierre(raw: any): PedidoPestanaCierre | null {
  if (!raw || typeof raw !== 'object') return null
  const objetivo = OBJETIVOS_CIERRE.find((o) => o === raw.objetivo)
  const target = str(raw.target_id).slice(0, 64)
  if (!objetivo || (raw.tipo !== 'tab' && raw.tipo !== 'workspace') || !target) return null
  return {
    objetivo,
    tipo: raw.tipo,
    target_id: target,
    label: str(raw.label).slice(0, 200),
    workspace_label: str(raw.workspace_label).slice(0, 200),
    carpeta: str(raw.carpeta).slice(0, 400),
    sesiones: contador(raw.sesiones),
    terminales: contador(raw.terminales),
  }
}

export function normalizeVistaCierrePedido(raw: unknown): VistaCierrePedido | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.trabajando !== 'boolean' || typeof o.huella !== 'string') return null
  const estados = Array.isArray(o.estados) ? o.estados.filter((e): e is string => typeof e === 'string') : []
  return { trabajando: o.trabajando, estados, huella: o.huella }
}

/** Acciones que pide una sesión por el MCP: sin sus datos no hay qué mostrar ni qué aprobar. */
function pedidoMcp(out: PedidoPestana, p: any): PedidoPestana | null {
  const { pestanas: _p, tarjeta: _t, ...base } = out
  if (p.accion === 'mensaje') {
    const pane = str(p.envio?.pane_id)
    if (!pane) return null
    return { ...base, accion: 'mensaje', envio: { pane_id: pane.slice(0, 64), nombre: str(p.envio.nombre).slice(0, 120) } }
  }
  if (p.accion === 'programada') {
    const cuando = str(p.programada?.cuando)
    const pane = str(p.programada?.pane_id)
    if (!/^\d{1,2}:\d{2}$/.test(cuando) || !pane) return null
    return {
      ...base,
      accion: 'programada',
      programada: { cuando, pane_id: pane.slice(0, 64), nombre: str(p.programada.nombre).slice(0, 120) },
    }
  }
  const ticket = str(p.tarea?.ticket)
  if (!ticket) return null
  return { ...base, accion: 'tarea', tarea: { ticket: ticket.slice(0, 20) } }
}

export function normalizePedidosPestana(raw: unknown): PedidoPestana[] {
  const list = Array.isArray(raw) ? raw : []
  return list
    .filter((p) => p && typeof p === 'object')
    .map((p: any) => {
      const id = PEDIDO_PESTANA_ID_RE.test(str(p.id)) ? str(p.id) : ''
      const ts = Number(p.ts)
      const vence = Number(p.vence)
      const pane = str(p?.origen?.pane_id)
      const nombre = str(p?.origen?.nombre)
      if (!id || !Number.isFinite(ts) || !Number.isFinite(vence) || !pane || !nombre) return null
      const out: PedidoPestana = {
        id,
        carpeta: str(p.carpeta).slice(0, 400),
        mensaje: str(p.mensaje).slice(0, 8000),
        origen: { pane_id: pane, nombre: nombre.slice(0, 120), session_id: str(p?.origen?.session_id).slice(0, 64) },
        ts,
        vence,
      }
      const nom = str(p.nombre)
      if (nom) out.nombre = nom.slice(0, 120)
      const tarj = str(p.tarjeta)
      if (tarj) out.tarjeta = tarj.slice(0, 120)
      const pest = Array.isArray(p.pestanas) ? p.pestanas : null
      if (pest?.length) {
        const tabs: PedidoPestanaTab[] = []
        for (const t of pest) {
          if (!t || typeof t !== 'object') continue
          const tn = str((t as any).nombre)
          const tipo = (t as any).tipo
          if (!tn || (tipo !== 'claude' && tipo !== 'terminal')) continue
          const tab: PedidoPestanaTab = {
            nombre: tn.slice(0, 120),
            tipo,
            carpeta: str((t as any).carpeta || p.carpeta).slice(0, 400),
          }
          const msg = str((t as any).mensaje)
          if (msg) tab.mensaje = msg.slice(0, 8000)
          const cmd = str((t as any).comando)
          if (cmd) tab.comando = cmd.slice(0, 500)
          tabs.push(tab)
        }
        if (tabs.length) out.pestanas = tabs
      }
      const leyo = p.leyo_otra_sesion
      if (leyo && typeof leyo === 'object' && str(leyo.nombre) && typeof leyo.ts === 'number' && Number.isFinite(leyo.ts)) {
        out.leyo_otra_sesion = { nombre: str(leyo.nombre).slice(0, 120), ts: leyo.ts }
      }
      if (p.accion === 'mensaje' || p.accion === 'programada' || p.accion === 'tarea') return pedidoMcp(out, p)
      if (p.accion === 'cursor') return pedidoCursor(out, p)
      if (p.accion === 'cerrar' && p.cierre !== undefined) {
        const cierre = pedidoCierre(p.cierre)
        if (!cierre) return null
        const { pestanas: _p, tarjeta: _t, terminal: _x, ...resto } = out
        return { ...resto, accion: 'cerrar', cierre }
      }
      if (p.accion !== undefined) {
        const t = p.terminal
        const tpane = str(t?.pane_id)
        if (p.accion !== 'cerrar' || !tpane) return null
        out.accion = 'cerrar'
        out.terminal = {
          pane_id: tpane.slice(0, 64),
          titulo: str(t.titulo).slice(0, 200),
          cwd: str(t.cwd).slice(0, 400),
          proceso: str(t.proceso).slice(0, 120),
          estado: str(t.estado).slice(0, 20),
          donde: str(t.donde).slice(0, 200),
        }
      }
      return out
    })
    .filter((p): p is PedidoPestana => p !== null)
}

export function normalizePedidoPestanaEvento(raw: unknown): { id: string; estado: PedidoPestanaEstado } | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const id = PEDIDO_PESTANA_ID_RE.test(str(o.id)) ? str(o.id) : ''
  const estado = PEDIDO_ESTADOS.includes(o.estado as PedidoPestanaEstado) ? (o.estado as PedidoPestanaEstado) : null
  if (!id || !estado) return null
  return { id, estado }
}

const SUB_ESTADOS: SubagenteEstado[] = ['trabajando', 'termino', 'sin_actividad']

export function normalizeSubagentes(raw: any): Subagente[] {
  const items: any[] = Array.isArray(raw?.items) ? raw.items : []
  return items
    .filter((r) => r && typeof r.id === 'string')
    .map((r) => ({
      id: r.id,
      descripcion: str(r.descripcion) || 'Subagente',
      tipo: str(r.tipo),
      modelo: str(r.modelo),
      estado: SUB_ESTADOS.includes(r.estado) ? r.estado : 'sin_actividad',
      inicio: str(r.inicio),
      segundos: Number.isFinite(Number(r.segundos)) ? Math.max(0, Number(r.segundos)) : 0,
      paso: str(r.paso),
      tokens: Number.isFinite(Number(r.tokens)) && r.tokens != null ? Number(r.tokens) : null,
    }))
}
