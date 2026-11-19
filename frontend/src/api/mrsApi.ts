import { ApiError } from './types'

export type PipeEstado = 'ok' | 'fallo' | 'corriendo' | 'cancelado' | 'manual' | 'sin'

export interface MrPersona {
  username: string
  nombre: string
}

export interface MrPipeline {
  estado: PipeEstado
  id: number
  url: string
}

export interface Mr {
  ref: string
  project_id: number
  iid: number
  repo: string
  repo_corto: string
  titulo: string
  rama: string
  target: string
  rol: 'autor' | 'revisor'
  autor: MrPersona
  draft: boolean
  conflictos: boolean
  estado_merge: string
  puede_mergear: boolean
  sha: string
  pipeline: MrPipeline
  aprobaciones: { dadas: number; requeridas: number; faltan: number; por: MrPersona[]; yo: boolean; puedo: boolean }
  reviewers: MrPersona[]
  hilos_sin_resolver: number
  comentarios_nuevos: number
  url: string
  actualizado: string
  creado: string
  pausado: boolean
}

export interface MrJob {
  id: number
  nombre: string
  etapa: string
  estado: PipeEstado
  status: string
  url: string
  duracion: number
  reintentable: boolean
  permitido_fallar: boolean
}

export interface MrNota {
  id: number
  autor: MrPersona
  cuerpo: string
  fecha: string
  mio: boolean
}

export interface MrHilo {
  id: string
  resoluble: boolean
  resuelto: boolean
  archivo: string
  linea: number
  notas: MrNota[]
}

export interface MrArchivo {
  path: string
  viejo: string
  nuevo: boolean
  borrado: boolean
  renombrado: boolean
  diff: string
  truncado: boolean
}

/** Nota de sistema de GitLab ("added 1 commit", "approved this merge request"…). */
export interface MrEvento {
  id: number
  autor: MrPersona
  cuerpo: string
  fecha: string
  mio: boolean
}

export interface MrDetalle extends Mr {
  descripcion: string
  jobs: MrJob[]
  hilos: MrHilo[]
  actividad: MrEvento[]
  archivos: MrArchivo[]
}

export interface MrsListado {
  items: Mr[]
  error: string
  actualizado: number
  refrescando: boolean
  disponible: boolean
  habilitado: boolean
  /** session_id → ref del MR de su rama. */
  sesiones: Record<string, string>
}

export interface MrRepo {
  path: string
  proyecto: string
  nombre: string
  rama: string
  ramas: string[]
}

export interface CrearOpciones {
  repos: MrRepo[]
  sugerido: { repo: string; rama: string }
  equipo: MrPersona[]
}

export interface RamaInfo {
  pusheada: boolean
  target: string
  existente: { ref: string; iid: number; url: string } | null
}

export interface NuevoMr {
  repo: string
  rama: string
  target: string
  titulo: string
  descripcion: string
  reviewers: string[]
  session_id?: string | null
}

export interface MrDestino {
  session_id: string
  pane_id: string
  nombre: string
  status: string
  carpeta_corta: string
  /** Trabaja en la rama de este MR o lo creó. */
  asociada: boolean
}

export interface MrDestinos {
  sugerida: string | null
  sesiones: MrDestino[]
}

export interface MrsApi {
  listar(): Promise<MrsListado>
  refrescar(): Promise<MrsListado>
  detalle(ref: string): Promise<MrDetalle>
  aprobar(ref: string, aprobar: boolean): Promise<void>
  comentar(ref: string, texto: string): Promise<void>
  reintentar(ref: string, cual: { pipeline_id: number } | { job_id: number }): Promise<void>
  reviewers(ref: string, usernames: string[]): Promise<void>
  draft(ref: string, draft: boolean): Promise<void>
  pausar(ref: string, pausar: boolean): Promise<void>
  pedirActualizar(ref: string): Promise<void>
  destinos(ref: string): Promise<MrDestinos>
  jobASesion(ref: string, jobId: number, sessionId: string): Promise<void>
  hiloASesion(ref: string, hiloId: string, sessionId: string): Promise<void>
  mergear(ref: string, pin: string, sha: string): Promise<void>
  cerrar(ref: string, pin: string): Promise<void>
  opciones(sessionId?: string): Promise<CrearOpciones>
  rama(repo: string, rama: string): Promise<RamaInfo>
  redactar(repo: string, rama: string, target: string): Promise<{ titulo: string; descripcion: string }>
  crear(body: NuevoMr): Promise<{ ref: string; url: string }>
}

export const REF_RE = /^(\d{1,12}):(\d{1,9})$/

/** `pid:iid` → segmento de URL; nada que no sean dos enteros llega a armar una ruta. */
export function refPath(ref: string): string {
  const m = REF_RE.exec(ref)
  if (!m) throw new ApiError(422, 'MR inválido')
  return `${m[1]}/${m[2]}`
}

const str = (v: unknown, max = 500) => (typeof v === 'string' ? v.slice(0, max) : '')
const int = (v: unknown) => (Number.isInteger(v) && (v as number) >= 0 ? (v as number) : 0)
const bool = (v: unknown) => v === true
const gitlabUrl = (v: unknown) => (typeof v === 'string' && v.startsWith('https://gitlab.com/') ? v : '')
const ESTADOS: PipeEstado[] = ['ok', 'fallo', 'corriendo', 'cancelado', 'manual', 'sin']
const estado = (v: unknown): PipeEstado => (ESTADOS.includes(v as PipeEstado) ? (v as PipeEstado) : 'sin')
const persona = (v: any): MrPersona => ({ username: str(v?.username, 80), nombre: str(v?.nombre, 120) })
const lista = (v: unknown): any[] => (Array.isArray(v) ? v : [])

export function normalizeMr(raw: any): Mr | null {
  const ref = str(raw?.ref, 30)
  if (!REF_RE.test(ref)) return null
  const ap = raw?.aprobaciones ?? {}
  return {
    ref,
    project_id: int(raw.project_id),
    iid: int(raw.iid),
    repo: str(raw.repo, 300),
    repo_corto: str(raw.repo_corto, 120),
    titulo: str(raw.titulo, 255),
    rama: str(raw.rama, 200),
    target: str(raw.target, 200),
    rol: raw.rol === 'revisor' ? 'revisor' : 'autor',
    autor: persona(raw.autor),
    draft: bool(raw.draft),
    conflictos: bool(raw.conflictos),
    estado_merge: str(raw.estado_merge, 40),
    puede_mergear: bool(raw.puede_mergear),
    sha: /^[0-9a-f]{40}$/.test(str(raw.sha, 40)) ? raw.sha : '',
    pipeline: { estado: estado(raw.pipeline?.estado), id: int(raw.pipeline?.id), url: gitlabUrl(raw.pipeline?.url) },
    aprobaciones: {
      dadas: int(ap.dadas),
      requeridas: int(ap.requeridas),
      faltan: int(ap.faltan),
      por: lista(ap.por).map(persona),
      yo: bool(ap.yo),
      puedo: bool(ap.puedo),
    },
    reviewers: lista(raw.reviewers).map(persona),
    hilos_sin_resolver: int(raw.hilos_sin_resolver),
    comentarios_nuevos: int(raw.comentarios_nuevos),
    url: gitlabUrl(raw.url),
    actualizado: str(raw.actualizado, 40),
    creado: str(raw.creado, 40),
    pausado: bool(raw.pausado),
  }
}

export function normalizeListado(raw: any): MrsListado {
  const sesiones: Record<string, string> = {}
  for (const [k, v] of Object.entries(raw?.sesiones ?? {})) if (typeof v === 'string' && REF_RE.test(v)) sesiones[k] = v
  return {
    items: lista(raw?.items).map(normalizeMr).filter((m): m is Mr => !!m),
    error: str(raw?.error, 300),
    actualizado: int(raw?.actualizado),
    refrescando: bool(raw?.refrescando),
    disponible: raw?.disponible !== false,
    habilitado: raw?.habilitado !== false,
    sesiones,
  }
}

export function normalizeDetalle(raw: any): MrDetalle | null {
  const base = normalizeMr(raw)
  if (!base) return null
  return {
    ...base,
    descripcion: str(raw.descripcion, 20000),
    jobs: lista(raw.jobs).map((j) => ({
      id: int(j?.id),
      nombre: str(j?.nombre, 120),
      etapa: str(j?.etapa, 80),
      estado: estado(j?.estado),
      status: str(j?.status, 30),
      url: gitlabUrl(j?.url),
      duracion: int(j?.duracion),
      reintentable: bool(j?.reintentable),
      permitido_fallar: bool(j?.permitido_fallar),
    })).filter((j) => j.id),
    hilos: lista(raw.hilos).map((h) => ({
      id: str(h?.id, 64),
      resoluble: bool(h?.resoluble),
      resuelto: bool(h?.resuelto),
      archivo: str(h?.archivo, 300),
      linea: int(h?.linea),
      notas: lista(h?.notas).map((n) => ({ id: int(n?.id), autor: persona(n?.autor), cuerpo: str(n?.cuerpo, 5000), fecha: str(n?.fecha, 40), mio: bool(n?.mio) })),
    })),
    actividad: lista(raw.actividad)
      .map((e) => ({ id: int(e?.id), autor: persona(e?.autor), cuerpo: str(e?.cuerpo, 400), fecha: str(e?.fecha, 40), mio: bool(e?.mio) }))
      .filter((e) => e.id),
    archivos: lista(raw.archivos).map((f) => ({
      path: str(f?.path, 400),
      viejo: str(f?.viejo, 400),
      nuevo: bool(f?.nuevo),
      borrado: bool(f?.borrado),
      renombrado: bool(f?.renombrado),
      diff: str(f?.diff, 20000),
      truncado: bool(f?.truncado),
    })),
  }
}

const SESSION_ID_RE = /^[A-Za-z0-9_.:-]{1,80}$/
const HILO_ID_RE = /^[0-9a-f]{8,64}$/

export function normalizeDestinos(raw: any): MrDestinos {
  const sesiones = lista(raw?.sesiones)
    .filter((x) => typeof x?.session_id === 'string' && SESSION_ID_RE.test(x.session_id))
    .map((x) => ({
      session_id: x.session_id as string,
      pane_id: str(x.pane_id, 64),
      nombre: str(x.nombre, 120),
      status: str(x.status, 30),
      carpeta_corta: str(x.carpeta_corta, 200),
      asociada: bool(x.asociada),
    }))
  const sugerida = typeof raw?.sugerida === 'string' && SESSION_ID_RE.test(raw.sugerida) ? raw.sugerida : null
  return { sugerida, sesiones }
}

function aSesionBody(sessionId: string) {
  if (!SESSION_ID_RE.test(sessionId)) throw new ApiError(422, 'Sesión inválida')
  return { session_id: sessionId }
}

async function call(path: string, body?: unknown): Promise<any> {
  let res: Response
  try {
    res = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.status === 401 ? 'La sesión venció, volvé a entrar' : 'GitLab no respondió'
    try {
      const d = await res.json()
      if (typeof d?.detail === 'string') detail = d.detail
    } catch {
      /* not json */
    }
    const ra = Number(res.headers.get('Retry-After'))
    throw new ApiError(res.status, detail, Number.isFinite(ra) && ra > 0 ? ra : null)
  }
  return res.json()
}

const q = (params: Record<string, string>) => new URLSearchParams(params).toString()

export const httpMrsApi: MrsApi = {
  listar: async () => normalizeListado(await call('/api/mrs')),
  refrescar: async () => normalizeListado(await call('/api/mrs/refrescar', {})),
  async detalle(ref) {
    const d = normalizeDetalle(await call(`/api/mrs/${refPath(ref)}`))
    if (!d) throw new ApiError(502, 'Respuesta ilegible')
    return d
  },
  aprobar: async (ref, aprobar) => void (await call(`/api/mrs/${refPath(ref)}/aprobar`, { aprobar })),
  comentar: async (ref, texto) => void (await call(`/api/mrs/${refPath(ref)}/comentar`, { texto })),
  reintentar: async (ref, cual) => void (await call(`/api/mrs/${refPath(ref)}/reintentar`, cual)),
  reviewers: async (ref, reviewers) => void (await call(`/api/mrs/${refPath(ref)}/reviewers`, { reviewers })),
  draft: async (ref, draft) => void (await call(`/api/mrs/${refPath(ref)}/draft`, { draft })),
  pausar: async (ref, pausar) => void (await call(`/api/mrs/${refPath(ref)}/pausa`, { pausar })),
  pedirActualizar: async (ref) => void (await call(`/api/mrs/${refPath(ref)}/pedir-actualizar`, {})),
  destinos: async (ref) => normalizeDestinos(await call(`/api/mrs/${refPath(ref)}/destinos`)),
  async jobASesion(ref, jobId, sessionId) {
    if (!Number.isInteger(jobId) || jobId <= 0) throw new ApiError(422, 'Job inválido')
    await call(`/api/mrs/${refPath(ref)}/jobs/${jobId}/a-sesion`, aSesionBody(sessionId))
  },
  async hiloASesion(ref, hiloId, sessionId) {
    if (!HILO_ID_RE.test(hiloId)) throw new ApiError(422, 'Comentario inválido')
    await call(`/api/mrs/${refPath(ref)}/hilos/${hiloId}/a-sesion`, aSesionBody(sessionId))
  },
  mergear: async (ref, pin, sha) => void (await call(`/api/mrs/${refPath(ref)}/mergear`, { pin, sha })),
  cerrar: async (ref, pin) => void (await call(`/api/mrs/${refPath(ref)}/cerrar`, { pin })),
  async opciones(sessionId) {
    const raw = await call(`/api/mrs/crear/opciones${sessionId ? `?${q({ session_id: sessionId })}` : ''}`)
    return {
      repos: lista(raw?.repos).map((r) => ({ path: str(r?.path), proyecto: str(r?.proyecto, 300), nombre: str(r?.nombre, 120), rama: str(r?.rama, 200), ramas: lista(r?.ramas).map((x) => str(x, 200)).filter(Boolean) })).filter((r) => r.path),
      sugerido: { repo: str(raw?.sugerido?.repo), rama: str(raw?.sugerido?.rama, 200) },
      equipo: lista(raw?.equipo).map(persona).filter((p) => p.username),
    }
  },
  async rama(repo, rama) {
    const raw = await call(`/api/mrs/crear/rama?${q({ repo, rama })}`)
    const ex = raw?.existente
    return {
      pusheada: bool(raw?.pusheada),
      target: str(raw?.target, 200),
      existente: ex && REF_RE.test(str(ex.ref, 30)) ? { ref: ex.ref, iid: int(ex.iid), url: gitlabUrl(ex.url) } : null,
    }
  },
  async redactar(repo, rama, target) {
    const raw = await call('/api/mrs/crear/redactar', { repo, rama, target })
    return { titulo: str(raw?.titulo, 255), descripcion: str(raw?.descripcion, 20000) }
  },
  async crear(body) {
    const raw = await call('/api/mrs/crear', body)
    return { ref: REF_RE.test(str(raw?.ref, 30)) ? raw.ref : '', url: gitlabUrl(raw?.url) }
  },
}

export const PIPE_LABEL: Record<PipeEstado, string> = {
  ok: 'Pipeline verde',
  fallo: 'Pipeline falló',
  corriendo: 'Pipeline corriendo',
  cancelado: 'Pipeline cancelado',
  manual: 'Esperando un paso manual',
  sin: 'Sin pipeline',
}
