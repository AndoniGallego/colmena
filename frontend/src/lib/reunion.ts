import { clipPalabras } from './estado'

export interface ReunionGuardada {
  titulo: string
  inicio: string
  fin: string
  duracion_s: number
  repos: string[]
  tema: string
  motivo: 'terminada' | 'sin_pc' | 'interrumpida' | 'llena'
  resumen: string[]
  pendientes: string[]
  tocadas: { texto: string; tipo: string; respuesta: string; archivos: string[] }[]
}

export const MOTIVO_LABEL: Record<ReunionGuardada['motivo'], string> = {
  terminada: 'Terminó normal',
  sin_pc: 'Se cortó: la PC dejó de avisar',
  interrumpida: 'Se interrumpió',
  llena: 'Llegó al tope de largo',
}

const MAX_LISTA = 40
const MAX_REPOS = 20
const MAX_TEXTO = 500
const MAX_ARCHIVOS = 20
const MOTIVOS = Object.keys(MOTIVO_LABEL)

/** Epoch en segundos (float) a "22 nov · 14:30"; "—" si no es un número usable. */
export function fechaReunion(v: unknown): string {
  if (typeof v !== 'number' || !Number.isFinite(v) || v <= 0) return '—'
  const d = new Date(v * 1000)
  if (Number.isNaN(d.getTime())) return '—'
  const dia = new Intl.DateTimeFormat('es-AR', { day: 'numeric', month: 'short' }).format(d)
  const hora = new Intl.DateTimeFormat('es-AR', { hour: '2-digit', minute: '2-digit', hour12: false }).format(d)
  return `${dia} · ${hora}`
}

const txt = (v: unknown, limit = MAX_TEXTO): string => (typeof v === 'string' ? clipPalabras(v, limit) : '')

function lista(v: unknown, max: number, limit = MAX_TEXTO): string[] {
  if (!Array.isArray(v)) return []
  return v.map((x) => txt(x, limit)).filter(Boolean).slice(0, max)
}

function tocada(v: unknown): ReunionGuardada['tocadas'][number] | null {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  const o = v as Record<string, unknown>
  const texto = txt(o.texto)
  if (!texto) return null
  return { texto, tipo: txt(o.tipo, 40), respuesta: txt(o.respuesta, 1000), archivos: lista(o.archivos, MAX_ARCHIVOS, 200) }
}

export function toReunion(raw: unknown): ReunionGuardada | null {
  let v = raw
  if (typeof v === 'string') {
    try {
      v = JSON.parse(v)
    } catch {
      return null
    }
  }
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null
  const o = v as Record<string, unknown>
  const dur = typeof o.duracion_s === 'number' && Number.isFinite(o.duracion_s) && o.duracion_s > 0 ? Math.round(o.duracion_s) : 0
  const tocadas = Array.isArray(o.tocadas) ? o.tocadas.map(tocada).filter((t): t is NonNullable<typeof t> => !!t).slice(0, MAX_LISTA) : []
  return {
    titulo: txt(o.titulo, 120) || 'Reunión',
    inicio: fechaReunion(o.inicio),
    fin: fechaReunion(o.fin),
    duracion_s: dur,
    repos: lista(o.repos, MAX_REPOS, 80),
    tema: txt(o.tema, 200),
    motivo: (MOTIVOS.includes(o.motivo as string) ? o.motivo : 'interrumpida') as ReunionGuardada['motivo'],
    resumen: lista(o.resumen, MAX_LISTA),
    pendientes: lista(o.pendientes, MAX_LISTA),
    tocadas,
  }
}

/** "1 h 05 min", "12 min" o "45 s". */
export function duracionLabel(s: number): string {
  if (!(s > 0)) return '—'
  if (s < 60) return `${Math.round(s)} s`
  const m = Math.round(s / 60)
  return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`
}

