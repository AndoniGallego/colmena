import type { Agent, Board } from '../api/types'
import { hueDe } from './hue'
import { estadoEfectivo } from './fondo'
import type { TeTocaItem, TeTocaMotivo } from './teToca'

export type EstadoCelda = 'te-toca' | 'trabajando' | 'termino' | 'tranquila' | 'vacia'
export type EstadoSesion = Exclude<EstadoCelda, 'vacia'>
export const CELDAS = 6

export interface SesionNotch {
  pane_id: string
  session_id: string
  titulo: string
  donde: string
  estado: EstadoSesion
  motivo: TeTocaMotivo | null
  /** Tarjetas ```opciones que dejó la sesión al final; 0 si no hay. */
  preguntas: number
  desdeMs: number | null
  linea: string
  last_activity: string | null
  hue: number
}

export interface SesionesInput {
  board: Board | null
  items: TeTocaItem[]
  enviadas?: ReadonlySet<string>
}

const tabLabel = (label: string, i: number) => (label && !/^\d+$/.test(label) ? label : `tab ${label || i + 1}`)

function activityMs(iso: string | null | undefined): number {
  if (!iso) return 0
  const t = Date.parse(iso)
  return Number.isNaN(t) ? 0 : t
}

function excluido(ag: Agent, board: Board): boolean {
  if (!ag.session_id) return true
  if (board.self_pane_id && ag.pane_id === board.self_pane_id) return true
  return false
}

function estadoDe(
  ag: Agent,
  item: TeTocaItem | undefined,
  enviadas: ReadonlySet<string> | undefined,
): EstadoSesion {
  const sid = ag.session_id!
  if (item?.motivo === 'pedido') return 'te-toca'
  if (
    item &&
    (item.motivo === 'permiso' || item.motivo === 'pregunta') &&
    !enviadas?.has(sid)
  ) {
    return 'te-toca'
  }
  const eff = estadoEfectivo(ag)
  if (eff === 'working' || eff === 'fondo' || enviadas?.has(sid)) return 'trabajando'
  if (item?.motivo === 'terminada') return 'termino'
  return 'tranquila'
}

export function sesionesNotch(i: SesionesInput): SesionNotch[] {
  const { board, items, enviadas } = i
  if (!board) return []
  const porSid = new Map(items.map((it) => [it.sid, it]))
  const out: SesionNotch[] = []
  for (const ws of board.workspaces) {
    const wsLabel = ws.label || `Workspace ${ws.number}`
    const hue = hueDe(wsLabel)
    ws.tabs.forEach((tab, ti) => {
      const donde = `${wsLabel} · ${tabLabel(tab.label, ti)}`
      for (const ag of tab.agents) {
        if (excluido(ag, board)) continue
        const item = porSid.get(ag.session_id!)
        const estado = estadoDe(ag, item, enviadas)
        out.push({
          pane_id: ag.pane_id,
          session_id: ag.session_id!,
          titulo: ag.title || donde,
          donde: item?.nombre ?? donde,
          estado,
          motivo: item?.motivo ?? null,
          preguntas: ag.preguntas ?? 0,
          desdeMs: estado === 'te-toca' && item ? item.desdeMs : null,
          linea: ag.doing || ag.title,
          last_activity: ag.last_activity,
          hue: item?.hue ?? hue,
        })
      }
    })
  }
  return out
}

export type Asignacion = readonly (string | null)[]

function cmpTeToca(a: SesionNotch, b: SesionNotch): number {
  return (a.desdeMs ?? 0) - (b.desdeMs ?? 0)
}

function cmpActividadDesc(a: SesionNotch, b: SesionNotch): number {
  return activityMs(b.last_activity) - activityMs(a.last_activity)
}

export function elegirSesiones(s: SesionNotch[]): SesionNotch[] {
  const teToca = s.filter((x) => x.estado === 'te-toca').sort(cmpTeToca)
  const trabajando = s.filter((x) => x.estado === 'trabajando').sort(cmpActividadDesc)
  const resto = s
    .filter((x) => x.estado !== 'te-toca' && x.estado !== 'trabajando')
    .sort(cmpActividadDesc)
  return [...teToca, ...trabajando, ...resto].slice(0, CELDAS)
}

export function asignarCeldas(prev: Asignacion, s: SesionNotch[]): (string | null)[] {
  const chosen = elegirSesiones(s)
  const chosenPanes = new Set(chosen.map((x) => x.pane_id))
  const base: (string | null)[] =
    prev.length === 0 ? Array.from({ length: CELDAS }, () => null) : [...prev]
  while (base.length < CELDAS) base.push(null)
  const result = base.slice(0, CELDAS)

  for (let i = 0; i < CELDAS; i++) {
    const p = result[i]
    if (p && !chosenPanes.has(p)) result[i] = null
  }

  const placed = new Set(result.filter(Boolean) as string[])
  const free: number[] = []
  for (let i = 0; i < CELDAS; i++) if (!result[i]) free.push(i)

  for (const ses of chosen) {
    if (placed.has(ses.pane_id)) continue
    const slot = free.shift()
    if (slot === undefined) break
    result[slot] = ses.pane_id
    placed.add(ses.pane_id)
  }

  return result
}

export function estadosCeldas(a: Asignacion, s: SesionNotch[]): EstadoCelda[] {
  const porPane = new Map(s.map((x) => [x.pane_id, x.estado]))
  const out: EstadoCelda[] = []
  for (let i = 0; i < CELDAS; i++) {
    const p = a[i] ?? null
    out.push(p ? (porPane.get(p) ?? 'vacia') : 'vacia')
  }
  return out
}

export interface Grupos {
  teToca: SesionNotch[]
  trabajando: SesionNotch[]
  termino: SesionNotch[]
  otras: SesionNotch[]
  fuera: number
}

export function gruposPanel(a: Asignacion, s: SesionNotch[]): Grupos {
  const byPane = new Map(s.map((x) => [x.pane_id, x]))
  const withCell = (a.filter(Boolean) as string[]).map((p) => byPane.get(p)).filter(Boolean) as SesionNotch[]
  const elegidas = elegirSesiones(s)
  const teToca = elegidas.filter((x) => x.estado === 'te-toca' && a.includes(x.pane_id))
  const trabajando = withCell.filter((x) => x.estado === 'trabajando').sort(cmpActividadDesc)
  const termino = withCell.filter((x) => x.estado === 'termino').sort(cmpActividadDesc)
  const inPanel = new Set([
    ...teToca.map((x) => x.pane_id),
    ...trabajando.map((x) => x.pane_id),
    ...termino.map((x) => x.pane_id),
  ])
  const otras = s.filter((x) => !inPanel.has(x.pane_id)).sort(cmpActividadDesc)
  return { teToca, trabajando, termino, otras, fuera: otras.length }
}

export interface Resumen {
  teToca: number
  trabajando: number
  termino: number
}

export const RETENER_RESUMEN_MS = 4500

/** true si el cambio es "una sesión dejó de trabajar" sin que aparezca nada que pida atención: conviene esperar el aviso. */
export function debeRetenerResumen(prev: Resumen, next: Resumen): boolean {
  if (next.trabajando >= prev.trabajando) return false
  if (next.teToca > prev.teToca) return false
  if (next.trabajando === prev.trabajando && next.teToca === prev.teToca && next.termino === prev.termino) return false
  return true
}

export function resumenNotch(s: SesionNotch[]): Resumen {
  let teToca = 0
  let trabajando = 0
  let termino = 0
  for (const x of s) {
    if (x.estado === 'te-toca') teToca++
    else if (x.estado === 'trabajando') trabajando++
    else if (x.estado === 'termino') termino++
  }
  return { teToca, trabajando, termino }
}

export function partesResumen(r: Resumen): { texto: string; alerta: boolean }[] {
  const out: { texto: string; alerta: boolean }[] = []
  if (r.teToca) {
    out.push({ texto: r.teToca === 1 ? '1 te toca' : `${r.teToca} te tocan`, alerta: true })
  }
  if (r.trabajando) {
    out.push({ texto: `${r.trabajando} trabajando`, alerta: false })
  }
  if (r.termino) {
    out.push({
      texto: r.termino === 1 ? '1 terminó' : `${r.termino} terminaron`,
      alerta: false,
    })
  }
  return out
}

export function textoResumen(r: Resumen): string {
  const partes = partesResumen(r)
  if (!partes.length) return 'Todo tranquilo'
  return partes.map((p) => p.texto).join(' · ')
}

const LARGO_OPCION_APILADA = 18

export function opcionesApiladas(labels: string[]): boolean {
  if (labels.length > 2) return true
  return labels.some((l) => l.length > LARGO_OPCION_APILADA)
}

/** Si conviene animar el fundido de la línea de resumen en la cara del notch. */
export function debeFundirTextoResumen(prev: string, next: string, soft: boolean): boolean {
  if (soft || prev === next) return false
  if (prev === '') return false
  return true
}

export function celdasQueTerminan(prev: readonly EstadoCelda[], next: readonly EstadoCelda[]): number[] {
  const out: number[] = []
  const n = Math.min(prev.length, next.length, CELDAS)
  for (let i = 0; i < n; i++) {
    if (prev[i] !== 'termino' && next[i] === 'termino') out.push(i)
  }
  return out
}
