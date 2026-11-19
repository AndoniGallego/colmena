import type { DialogView, PedidoPermiso, PedidoPestana, PreguntaSesion, VistaCierrePedido } from '../api/types'
import { canApprove, toolTitle } from './dialogo'
import {
  ariaAceptarPedidoPestana,
  ariaRechazarPedidoPestana,
  botonPedidoPestana,
  detallePedidoPestana,
  dondeCierre,
  textoTrabajando,
  tituloPedidoPestana,
} from './pedidosPestana'

export type FormaRespuesta =
  | { tipo: 'opciones'; pregunta: string; opciones: string[]; otro: boolean; via: 'dialogo' | 'sesion' }
  | { tipo: 'permiso'; titulo: string; detalle: string; puedePermitir: boolean; via: 'dialogo' | 'pedido'; pedidoId?: string }
  | {
      tipo: 'pedido'
      pedidoId: string
      titulo: string
      detalle: string
      boton: string
      aviso: string
      enviando: boolean
      error: string
      /** Solo cierres: espacio e id del objetivo. */
      donde: string
      ariaAceptar: string
      ariaRechazar: string
    }
  | { tipo: 'abrir'; motivo: string }
  | { tipo: 'cargando' }

export function resumenEntrada(p: PedidoPermiso): string {
  const e = p.entrada
  if (e && typeof e === 'object') {
    if (typeof e.command === 'string') return e.command
    if (typeof e.file_path === 'string') return e.file_path
  }
  return ''
}

function formaDialogo(view: DialogView): FormaRespuesta {
  if (view.tipo === 'pregunta') {
    const qs = view.pregunta.preguntas
    if (qs.length === 1 && !qs[0].multi) {
      const q = qs[0]
      const texto = q.texto || q.header || ''
      return {
        tipo: 'opciones',
        pregunta: texto,
        opciones: q.opciones.map((o) => o.label),
        otro: q.otro,
        via: 'dialogo',
      }
    }
    return { tipo: 'abrir', motivo: 'Contestala en Colmena' }
  }
  if (view.tipo === 'permiso') {
    return {
      tipo: 'permiso',
      titulo: toolTitle(view.permiso),
      detalle: view.permiso.detalle,
      puedePermitir: canApprove(view.permiso, 'si'),
      via: 'dialogo',
    }
  }
  if (view.tipo === 'pedido' && (view.pedido.estado === 'abierto' || view.pedido.estado === 'enviando')) {
    return {
      tipo: 'permiso',
      titulo: view.pedido.herramienta,
      detalle: resumenEntrada(view.pedido),
      puedePermitir: true,
      via: 'pedido',
      pedidoId: view.pedido.id,
    }
  }
  return { tipo: 'abrir', motivo: 'Contestala en Colmena' }
}

function formaPregunta(p: PreguntaSesion): FormaRespuesta {
  if (p.preguntas.length > 1) return { tipo: 'abrir', motivo: `Tiene ${p.preguntas.length} preguntas` }
  const q = p.preguntas[0]
  if (!q?.opciones.length) return { tipo: 'abrir', motivo: 'Contestala en Colmena' }
  return { tipo: 'opciones', pregunta: q.pregunta, opciones: q.opciones.map((o) => o.label), otro: true, via: 'sesion' }
}

export function formaRespuesta(view: DialogView | null, cargando: boolean, pregunta?: PreguntaSesion | null): FormaRespuesta {
  if (pregunta) return formaPregunta(pregunta)
  if (view) return formaDialogo(view)
  if (cargando) return { tipo: 'cargando' }
  return { tipo: 'abrir', motivo: 'Contestala en Colmena' }
}

export function formaPedido(
  p: PedidoPestana,
  accion?: { enviando?: boolean; error?: string; vista?: VistaCierrePedido },
): FormaRespuesta {
  const vista = accion?.vista
  return {
    tipo: 'pedido',
    pedidoId: p.id,
    titulo: tituloPedidoPestana(p),
    detalle: detallePedidoPestana(p),
    boton: botonPedidoPestana(p, vista),
    aviso: vista?.trabajando ? textoTrabajando(vista.estados) : '',
    enviando: !!accion?.enviando,
    error: accion?.error ?? '',
    donde: p.accion === 'cerrar' && p.cierre ? dondeCierre(p.cierre) : '',
    ariaAceptar: ariaAceptarPedidoPestana(p, vista),
    ariaRechazar: ariaRechazarPedidoPestana(p),
  }
}
