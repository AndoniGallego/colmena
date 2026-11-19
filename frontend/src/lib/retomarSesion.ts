import type { GrupoItem } from './nuevaTerminal'
import { validarNombreNueva } from './nuevaTerminal'

export type SesionVieja = {
  session_id: string
  titulo: string
  carpeta: string
  ultimo_ts: string
  ultima_frase: string
}

export type RetomarSesionBody = {
  id: string
  session_id: string
  nombre?: string
  grupo?: string
  nombre_tarjeta?: string
}

const GRUPO_RE = /^g\d{1,6}$/
const ID_RE = /^[A-Za-z0-9_-]{8,64}$/

export function filtrarSesionesViejas(lista: SesionVieja[], q: string): SesionVieja[] {
  const needle = q.trim().toLowerCase()
  if (!needle) return lista
  return lista.filter((s) => {
    const blob = `${s.titulo}\n${s.carpeta}\n${s.ultima_frase}`.toLowerCase()
    return blob.includes(needle)
  })
}

export function mensajeErrorRetomar(status: number, detail: string): string {
  if (status === 429) return 'Llegaste al tope de pestañas por hora'
  if (status === 409 && detail.toLowerCase().includes('abierta')) return 'Esa sesión ya está abierta en el tablero'
  if (status === 400 || status === 404) return 'Esa sesión ya no se puede retomar'
  return 'No pude retomarla'
}

export function armarCuerpoRetomar(
  sesion: SesionVieja,
  nombre: string,
  grupoId: string,
  nombreTarjeta: string,
  opId: string,
): RetomarSesionBody | null {
  if (!ID_RE.test(opId)) return null
  const err = validarNombreNueva(nombre)
  if (err) return null
  const body: RetomarSesionBody = { id: opId, session_id: sesion.session_id }
  const t = nombre.trim()
  if (t) body.nombre = t
  if (grupoId && GRUPO_RE.test(grupoId)) {
    body.grupo = grupoId
  } else {
    const nt = (nombreTarjeta || nombre).trim()
    if (nt) body.nombre_tarjeta = nt
  }
  return body
}

export function idOperacionRetomar(): string {
  const base = crypto.randomUUID().replace(/-/g, '')
  return `rs${base}`.slice(0, 32)
}

export function gruposParaRetomar(grupos: GrupoItem[]): GrupoItem[] {
  return grupos
}
