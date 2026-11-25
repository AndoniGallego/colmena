import { PEDIDO_PESTANA_ID_RE } from '../api/normalize'
import type { PedidoPestana, PedidoPestanaCierre, VistaCierrePedido } from '../api/types'

export const PEDIDO_ID_RE = PEDIDO_PESTANA_ID_RE

export function pedidoIdDesdeBusqueda(search: string): string | null {
  const id = new URLSearchParams(search).get('pedido')
  return id && PEDIDO_ID_RE.test(id) ? id : null
}

/** Quita `pedido` de la URL conservando pathname y el resto de parámetros. */
export function limpiarPedidoEnUrl(pathAndSearch: string): string {
  const u = new URL(pathAndSearch, 'http://local')
  u.searchParams.delete('pedido')
  const q = u.searchParams.toString()
  return u.pathname + (q ? `?${q}` : '')
}

export function textoVencePedidoPestana(venceS: number, ahoraS: number): string {
  const restante = Math.ceil((venceS - ahoraS) / 60)
  if (restante <= 0) return 'venció'
  if (restante === 1) return 'vence en 1 min'
  return `vence en ${restante} min`
}

export function mensajeErrorAbrirPedidoPestana(status: number): string {
  if (status === 404) return 'Ya no está disponible'
  if (status === 409) return 'Ya se decidió'
  if (status === 429) return 'Llegaste al tope de pestañas por hora'
  return 'No pude abrir la pestaña'
}

export function nombreSesionPedidoPestana(p: { origen: { nombre: string }; nombre?: string }): string {
  return p.nombre?.trim() || p.origen.nombre.trim() || 'Una sesión'
}

export function recortarCarpeta(carpeta: string, max = 48): string {
  const t = carpeta.trim()
  if (t.length <= max) return t
  return `…${t.slice(-max + 1)}`
}

/** Un mensaje que no entra en 4 líneas lleva "Ver todo". */
export function mensajeLargo(texto: string | undefined, lineas = 4, chars = 240): boolean {
  const t = (texto ?? '').trim()
  return t.split('\n').length > lineas || t.length > chars
}

/** Si el pedido va a pegar un mensaje escrito por otra sesión en alguna sesión nueva de Claude. */
export function hayMensajeParaClaude(p: {
  mensaje: string
  pestanas?: { tipo: 'claude' | 'terminal'; mensaje?: string }[]
}): boolean {
  if (p.pestanas?.length) return p.pestanas.some((t) => t.tipo === 'claude' && !!t.mensaje?.trim())
  return !!p.mensaje.trim()
}

const TITULO_MCP = { mensaje: 'Mandar mensaje', programada: 'Mensaje programado', tarea: 'Tarea de ticket' } as const
const BOTON_MCP = { mensaje: 'Mandar', programada: 'Programar', tarea: 'Crear' } as const
const ARIA_MCP = {
  mensaje: ['Mandar el mensaje', 'No mandar'],
  programada: ['Programar el mensaje', 'No programar'],
  tarea: ['Crear la tarea', 'No crear'],
} as const

function accionMcp(p: PedidoPestana): 'mensaje' | 'programada' | 'tarea' | null {
  return p.accion === 'mensaje' || p.accion === 'programada' || p.accion === 'tarea' ? p.accion : null
}

export function tituloPedidoPestana(p: PedidoPestana): string {
  const mcp = accionMcp(p)
  if (mcp) return TITULO_MCP[mcp]
  if (p.accion === 'cursor') return 'Trabajador Cursor'
  if (p.accion === 'cerrar') {
    if (!p.cierre) return 'Cerrar terminal'
    return { sesion: 'Cerrar sesión', pestana: 'Cerrar pestaña', tarjeta: 'Cerrar tarjeta' }[p.cierre.objetivo]
  }
  if (p.tarjeta?.trim()) return 'Abrir tarjeta'
  return (p.pestanas?.length ?? 0) > 1 ? 'Abrir pestañas' : 'Abrir pestaña'
}

export function botonPedidoPestana(p: PedidoPestana, vista?: VistaCierrePedido): string {
  const mcp = accionMcp(p)
  if (mcp) return BOTON_MCP[mcp]
  if (p.accion === 'cerrar') return p.cierre && vista?.trabajando ? 'Cerrar igual' : 'Cerrar'
  return p.accion === 'cursor' ? 'Lanzar' : 'Abrir'
}

const OBJETIVO_TXT = { sesion: 'sesión', pestana: 'pestaña', tarjeta: 'tarjeta' } as const

/** Espacio e id del objetivo: el título lo puede cambiar la terminal, el id no. */
export function dondeCierre(c: Pick<PedidoPestanaCierre, 'workspace_label' | 'target_id'>): string {
  return [c.workspace_label?.trim(), c.target_id].filter(Boolean).join(' · ')
}

export function ariaAceptarPedidoPestana(p: PedidoPestana, vista?: VistaCierrePedido): string {
  if (p.accion === 'cerrar' && p.cierre) {
    const o = OBJETIVO_TXT[p.cierre.objetivo]
    return vista?.trabajando ? `Cerrar la ${o} igual` : `Cerrar la ${o}`
  }
  if (p.accion === 'cerrar') return 'Cerrar la terminal'
  const mcp = accionMcp(p)
  if (mcp) return ARIA_MCP[mcp][0]
  if (p.accion === 'cursor') return 'Lanzar el trabajador Cursor'
  return (p.pestanas?.length ?? 0) > 0 ? 'Abrir pestañas' : 'Abrir pestaña'
}

export function ariaRechazarPedidoPestana(p: PedidoPestana): string {
  const mcp = accionMcp(p)
  if (mcp) return ARIA_MCP[mcp][1]
  if (p.accion === 'cerrar') return 'No cerrar'
  return p.accion === 'cursor' ? 'No lanzar' : 'No abrir'
}

export function textoTrabajando(estados: string[]): string {
  if (estados.includes('working')) return 'Está trabajando'
  if (estados.includes('blocked')) return 'Está esperando un permiso'
  if (estados.includes('fondo')) return 'Tiene trabajo en segundo plano'
  return 'No sé si está trabajando'
}

export function conteoCierre(c: PedidoPestanaCierre): string {
  const partes: string[] = []
  if (c.sesiones > 0) partes.push(`${c.sesiones} ${c.sesiones === 1 ? 'sesión' : 'sesiones'} de Claude`)
  if (c.terminales > 0) partes.push(`${c.terminales} ${c.terminales === 1 ? 'terminal' : 'terminales'}`)
  return partes.length ? partes.join(' · ') : 'Vacía'
}

/** Una línea para el notch. */
export function detallePedidoPestana(p: PedidoPestana): string {
  if (p.cierre) return p.cierre.objetivo === 'sesion' ? p.cierre.label : `${p.cierre.label} · ${conteoCierre(p.cierre)}`
  if (p.accion === 'cerrar') return p.terminal?.titulo || p.terminal?.proceso || 'Terminal'
  if (p.accion === 'cursor') return p.nombre ?? ''
  return p.tarjeta?.trim() || recortarCarpeta(p.carpeta, 40)
}
