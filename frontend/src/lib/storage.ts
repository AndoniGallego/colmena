import type { TraspasoChoice } from './traspaso'
import type { Drafts } from './drafts'
import { DEFAULT_LOGO, isLogoVariant, type LogoVariant } from './colmena'

const RESOLVED_KEY = 'orq.traspasos.resueltos'
const THEME_KEY = 'orq.theme'

export interface Resolution {
  choice: TraspasoChoice
  at: string
}

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function write(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage unavailable: state lives only in memory */
  }
}

export const loadResolutions = () => read<Record<string, Resolution>>(RESOLVED_KEY, {})

export function saveResolution(all: Record<string, Resolution>) {
  const entries = Object.entries(all).sort((a, b) => (a[1].at < b[1].at ? 1 : -1)).slice(0, 200)
  write(RESOLVED_KEY, Object.fromEntries(entries))
}

export type Theme = 'dark' | 'light'
export const loadTheme = (): Theme => (read<string>(THEME_KEY, 'dark') === 'light' ? 'light' : 'dark')
export const saveTheme = (t: Theme) => write(THEME_KEY, t)

const MOTION_KEY = 'orq.motion'
export type MotionPref = 'full' | 'soft'
export const loadMotion = (): MotionPref => (read<string>(MOTION_KEY, 'full') === 'soft' ? 'soft' : 'full')
export const saveMotion = (m: MotionPref) => write(MOTION_KEY, m)

const DRAFTS_KEY = 'orq.borradores'
export const loadDrafts = () => read<Drafts>(DRAFTS_KEY, {})
export const saveDrafts = (d: Drafts) => write(DRAFTS_KEY, d)

const BIB_KEY = 'orq.biblioteca'
export interface BibPrefs {
  layout: 'grid' | 'list'
  /** Ancho del visor como porcentaje del área, entre 40 y 65. */
  panel: number
  /** Última visita: lo posterior cuenta como nuevo. */
  visit: string
}
export const loadBibPrefs = (): BibPrefs => {
  const raw = read<Partial<BibPrefs>>(BIB_KEY, {})
  const panel = Number(raw.panel)
  return {
    layout: raw.layout === 'list' ? 'list' : 'grid',
    panel: Number.isFinite(panel) ? Math.min(65, Math.max(40, panel)) : 52,
    visit: typeof raw.visit === 'string' ? raw.visit : '',
  }
}
export const saveBibPrefs = (p: BibPrefs) => write(BIB_KEY, p)

const LIMPIEZA_KEY = 'orq.limpieza.dias'
export const loadLimpiezaDias = (): number | null => {
  const n = read<number | null>(LIMPIEZA_KEY, null)
  return typeof n === 'number' && Number.isInteger(n) && n >= 1 && n <= 30 ? n : null
}
export const saveLimpiezaDias = (n: number) => write(LIMPIEZA_KEY, n)

const BUSCADOR_KEY = 'orq.buscador.recientes'
export const loadRecientes = (): string[] => {
  const raw = read<unknown>(BUSCADOR_KEY, [])
  return Array.isArray(raw) ? raw.filter((x): x is string => typeof x === 'string').slice(0, 6) : []
}
export const saveRecientes = (ids: string[]) => write(BUSCADOR_KEY, ids)

const LOGO_KEY = 'orq.logo'
export const loadLogo = (): LogoVariant => {
  const v = read<unknown>(LOGO_KEY, DEFAULT_LOGO)
  return isLogoVariant(v) ? v : DEFAULT_LOGO
}
export const saveLogo = (v: LogoVariant) => write(LOGO_KEY, v)
