import { ApiError } from './types'

export interface CambioArchivo {
  path: string
  estado: string
  adds: number
  dels: number
  binario: boolean
  diff: string
  truncado: boolean
}

export interface CambioCommit {
  sha: string
  titulo: string
}

export interface Cambios {
  repo: boolean
  rama: string
  base: string
  commits: CambioCommit[]
  commits_total: number
  sin_guardar: number
  archivos: CambioArchivo[]
  truncado: boolean
}

const str = (v: unknown, max = 500) => (typeof v === 'string' ? v.slice(0, max) : '')
const num = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0)
const lista = (v: unknown): Record<string, unknown>[] => (Array.isArray(v) ? v.filter((x) => x && typeof x === 'object') : [])

export function normalizeCambios(raw: unknown): Cambios {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const commits = lista(r.commits)
    .map((c) => ({ sha: str(c.sha, 40), titulo: str(c.titulo, 300) }))
    .filter((c) => c.sha)
  const archivos = lista(r.archivos)
    .map((a) => ({
      path: str(a.path, 1000),
      estado: str(a.estado, 1) || 'M',
      adds: num(a.adds),
      dels: num(a.dels),
      binario: a.binario === true,
      diff: typeof a.diff === 'string' ? a.diff : '',
      truncado: a.truncado === true,
    }))
    .filter((a) => a.path)
  return {
    repo: r.repo === true,
    rama: str(r.rama, 200),
    base: str(r.base, 200),
    commits,
    commits_total: Math.max(num(r.commits_total), commits.length),
    sin_guardar: num(r.sin_guardar),
    archivos,
    truncado: r.truncado === true,
  }
}

export async function getCambios(sid: string, refrescar = false): Promise<Cambios> {
  let res: Response
  try {
    res = await fetch(`/api/sesiones/${encodeURIComponent(sid)}/cambios${refrescar ? '?refrescar=1' : ''}`, { credentials: 'same-origin' })
  } catch {
    throw new ApiError(0, 'Se cortó la conexión con el servidor')
  }
  if (!res.ok) {
    let detail = res.status === 401 ? 'La sesión venció, volvé a entrar' : 'No pude leer los cambios'
    try {
      const d = await res.json()
      if (typeof d?.detail === 'string') detail = d.detail
    } catch {
      /* not json */
    }
    throw new ApiError(res.status, detail)
  }
  return normalizeCambios(await res.json())
}
