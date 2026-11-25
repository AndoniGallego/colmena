import { coincideCtrlOCmd } from './teclas'

export type CarpetaItem = { ruta: string; nombre: string; repo?: boolean }

export type GrupoItem = { id: string; nombre: string; carpeta: string | null }

export type TipoNueva = 'shell' | 'claude'

export type NuevaTerminalBody = {
  carpeta: string
  tipo: TipoNueva
  id: string
  nombre?: string
  grupo?: string
}

const GRUPO_RE = /^g\d{1,6}$/

const ID_RE = /^[A-Za-z0-9_-]{8,64}$/
const CONTROL = /[\x00-\x1f\x7f-\x9f\u2028\u2029]/

export function filtrarCarpetas(carpetas: CarpetaItem[], q: string): CarpetaItem[] {
  const needle = q.trim().toLowerCase()
  if (!needle) return carpetas
  return carpetas.filter((c) => c.nombre.toLowerCase().includes(needle) || c.ruta.toLowerCase().includes(needle))
}

export function validarNombreNueva(raw: string): string {
  const t = raw.trim()
  if (!t) return ''
  if (t.length > 60) return 'Máximo 60 caracteres'
  if (CONTROL.test(t)) return 'Tiene caracteres no permitidos'
  return ''
}

export function placeholderNombre(c: CarpetaItem | null): string {
  return c?.nombre ?? ''
}

export function carpetaSugerida(grupoId: string | null, grupos: GrupoItem[], carpetas: CarpetaItem[]): CarpetaItem | null {
  if (!grupoId) return null
  const g = grupos.find((x) => x.id === grupoId)
  if (!g?.carpeta) return null
  return carpetas.find((c) => c.ruta === g.carpeta) ?? null
}

export function armarCuerpoNueva(
  carpeta: CarpetaItem,
  tipo: TipoNueva,
  nombre: string,
  id: string,
  grupo: string | null,
): NuevaTerminalBody {
  const body: NuevaTerminalBody = { carpeta: carpeta.ruta, tipo, id }
  const t = nombre.trim()
  if (t) body.nombre = t
  if (grupo && GRUPO_RE.test(grupo)) body.grupo = grupo
  return body
}

export function idOperacionNueva(): string {
  const base = crypto.randomUUID().replace(/-/g, '')
  return `nt${base}`.slice(0, 32)
}

export function idValido(id: string): boolean {
  return ID_RE.test(id)
}

export type ModoNueva = 'terminal' | 'tarea'

export type NuevaTareaBody = {
  id: string
  repo: string
  tarea: string
  nombre?: string
  rama?: string
  ticket?: string
  grupo?: string
}

export type NuevaTareaResult = { ok: true; pane_id: string; ruta: string; rama: string; pegado?: false }

export const MAX_TAREA = 4000
// Con ticket, el back antepone ~280 caracteres de instrucciones (nueva_tarea.mensaje_ticket) dentro del mismo tope.
export const MAX_NOTA_TICKET = 3700

const MODO_KEY = 'orq.nuevaModo'
const REPO_KEY = 'orq.nuevaRepo'
export const TICKET_RE = /^[A-Z][A-Z0-9]{1,9}-[1-9][0-9]{0,5}$/
const RAMA_RE = /^[A-Za-z0-9][A-Za-z0-9._/-]{0,79}$/

function leer(key: string): string {
  try {
    return localStorage.getItem(key) ?? ''
  } catch {
    return ''
  }
}

function guardar(key: string, valor: string): void {
  try {
    localStorage.setItem(key, valor)
  } catch {
    /* sin almacenamiento: se recuerda solo mientras la página está abierta */
  }
}

export function leerModo(): ModoNueva {
  return leer(MODO_KEY) === 'tarea' ? 'tarea' : 'terminal'
}

export function guardarModo(modo: ModoNueva): void {
  guardar(MODO_KEY, modo)
}

export function leerUltimoRepo(): string {
  return leer(REPO_KEY)
}

export function guardarUltimoRepo(ruta: string): void {
  guardar(REPO_KEY, ruta)
}

export function soloRepos(carpetas: CarpetaItem[]): CarpetaItem[] {
  return carpetas.filter((c) => c.repo === true)
}

export function repoInicial(repos: CarpetaItem[], ultimo: string, grupoCarpeta: string | null): CarpetaItem | null {
  const por = (ruta: string | null) => (ruta ? repos.find((r) => r.ruta === ruta) : undefined)
  return por(grupoCarpeta) ?? por(ultimo) ?? repos[0] ?? null
}

export function validarTicket(raw: string): string {
  const t = raw.trim()
  if (!t) return ''
  return TICKET_RE.test(t.toUpperCase()) ? '' : 'Ese ticket no tiene forma de clave de Jira (p. ej. ABC-123)'
}

export function ramaDeTicket(raw: string): string {
  const t = raw.trim().toUpperCase()
  return t && TICKET_RE.test(t) ? `feature/${t}` : ''
}

export function validarTarea(raw: string, ticket = ''): string {
  const t = raw.trim()
  if (!t && !ramaDeTicket(ticket)) return 'Contá qué hay que hacer'
  const tope = ramaDeTicket(ticket) ? MAX_NOTA_TICKET : MAX_TAREA
  if (t.length > tope) return `Máximo ${tope} caracteres`
  return ''
}

export function validarRamaNueva(raw: string): string {
  const t = raw.trim()
  if (!t) return ''
  const malo =
    !RAMA_RE.test(t) || t.includes('..') || t.includes('//') || t.endsWith('/') || t.endsWith('.') || t.split('/').some((p) => p.startsWith('.') || p.endsWith('.lock'))
  return malo ? 'Usá letras, números, guiones y barras' : ''
}

export function armarCuerpoTarea(repo: CarpetaItem, tarea: string, nombre: string, rama: string, id: string, ticket = '', grupo = ''): NuevaTareaBody {
  const body: NuevaTareaBody = { id, repo: repo.ruta, tarea: tarea.trim() }
  if (grupo) body.grupo = grupo
  if (nombre.trim()) body.nombre = nombre.trim()
  if (ticket.trim()) body.ticket = ticket.trim().toUpperCase()
  else if (rama.trim()) body.rama = rama.trim()
  return body
}

export function esAtajoEnviar(e: { key: string; ctrlKey: boolean; metaKey: boolean; altKey?: boolean; shiftKey?: boolean }, combo: string = 'mod+enter'): boolean {
  return coincideCtrlOCmd(e, combo)
}
