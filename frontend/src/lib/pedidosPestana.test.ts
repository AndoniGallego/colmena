import { describe, expect, it } from 'vitest'
import type { PedidoPestana, PedidoPestanaCierre } from '../api/types'
import {
  PEDIDO_ID_RE,
  botonPedidoPestana,
  conteoCierre,
  ariaAceptarPedidoPestana,
  ariaRechazarPedidoPestana,
  detallePedidoPestana,
  dondeCierre,
  textoTrabajando,
  tituloPedidoPestana,
  hayMensajeParaClaude,
  limpiarPedidoEnUrl,
  mensajeLargo,
  mensajeErrorAbrirPedidoPestana,
  pedidoIdDesdeBusqueda,
  textoVencePedidoPestana,
} from './pedidosPestana'

describe('lib/pedidosPestana', () => {
  it('lee y valida ?pedido=', () => {
    expect(pedidoIdDesdeBusqueda('?pedido=550e8400-e29b-41d4-a716-446655440000')).toBe('550e8400-e29b-41d4-a716-446655440000')
    expect(pedidoIdDesdeBusqueda('?pedido=no-es-uuid&x=1')).toBeNull()
    expect(pedidoIdDesdeBusqueda('')).toBeNull()
    expect(PEDIDO_ID_RE.test('550e8400-e29b-41d4-a716-446655440000')).toBe(true)
  })

  it('limpiarPedidoEnUrl saca pedido y conserva el resto', () => {
    const out = limpiarPedidoEnUrl('/?pedido=550e8400-e29b-41d4-a716-446655440000&terminal=g1:p1')
    expect(out).toBe('/?terminal=g1%3Ap1')
  })

  it('textoVencePedidoPestana en minutos', () => {
    expect(textoVencePedidoPestana(1000, 520)).toBe('vence en 8 min')
    expect(textoVencePedidoPestana(100, 200)).toBe('venció')
  })

  it('mensajes de error de abrir', () => {
    expect(mensajeErrorAbrirPedidoPestana(404)).toBe('Ya no está disponible')
    expect(mensajeErrorAbrirPedidoPestana(409)).toBe('Ya se decidió')
    expect(mensajeErrorAbrirPedidoPestana(429)).toBe('Llegaste al tope de pestañas por hora')
  })

  it('mensajeLargo: más de 4 líneas o más de 240 caracteres', () => {
    expect(mensajeLargo('corto')).toBe(false)
    expect(mensajeLargo('a\nb\nc\nd')).toBe(false)
    expect(mensajeLargo('a\nb\nc\nd\ne')).toBe(true)
    expect(mensajeLargo('x'.repeat(241))).toBe(true)
    expect(mensajeLargo(undefined)).toBe(false)
  })

  it('hayMensajeParaClaude mira el pedido de una pestaña y las pestañas claude', () => {
    expect(hayMensajeParaClaude({ mensaje: 'hola' })).toBe(true)
    expect(hayMensajeParaClaude({ mensaje: '  ' })).toBe(false)
    expect(hayMensajeParaClaude({ mensaje: '', pestanas: [{ tipo: 'terminal', mensaje: 'x' }] })).toBe(false)
    expect(hayMensajeParaClaude({ mensaje: '', pestanas: [{ tipo: 'claude', mensaje: 'x' }] })).toBe(true)
    expect(hayMensajeParaClaude({ mensaje: 'ignorado', pestanas: [{ tipo: 'claude' }] })).toBe(false)
  })
})

const abrirBase: PedidoPestana = {
  id: '550e8400-e29b-41d4-a716-446655440000',
  carpeta: '/home/usuario/proyecto',
  mensaje: 'hola',
  origen: { pane_id: 'w1:p1', nombre: 'Origen', session_id: '' },
  ts: 1,
  vence: 2,
}
const cierreBase: PedidoPestanaCierre = {
  objetivo: 'pestana',
  tipo: 'tab',
  target_id: 'w1:t1',
  label: 'API',
  workspace_label: 'Tienda',
  carpeta: '/home/usuario/proyecto',
  sesiones: 1,
  terminales: 2,
}
const cierre = (objetivo: PedidoPestanaCierre['objetivo']): PedidoPestana => ({
  ...abrirBase,
  accion: 'cerrar',
  cierre: { ...cierreBase, objetivo },
})

describe('lib/pedidosPestana: cierre', () => {
  it('títulos por tipo de pedido', () => {
    expect(tituloPedidoPestana(abrirBase)).toBe('Abrir pestaña')
    expect(tituloPedidoPestana(cierre('sesion'))).toBe('Cerrar sesión')
    expect(tituloPedidoPestana(cierre('pestana'))).toBe('Cerrar pestaña')
    expect(tituloPedidoPestana(cierre('tarjeta'))).toBe('Cerrar tarjeta')
    expect(tituloPedidoPestana({ ...abrirBase, accion: 'cursor' })).toBe('Trabajador Cursor')
    expect(tituloPedidoPestana({ ...abrirBase, accion: 'cerrar' })).toBe('Cerrar terminal')
    const tab = { nombre: 'a', tipo: 'terminal' as const, carpeta: '/x' }
    expect(tituloPedidoPestana({ ...abrirBase, pestanas: [tab, tab] })).toBe('Abrir pestañas')
    expect(tituloPedidoPestana({ ...abrirBase, tarjeta: 'Nueva', pestanas: [tab, tab] })).toBe('Abrir tarjeta')
  })
  it('botón Cerrar igual solo con la vista trabajando', () => {
    expect(botonPedidoPestana(cierre('pestana'))).toBe('Cerrar')
    expect(botonPedidoPestana(cierre('pestana'), { trabajando: false, estados: [], huella: 'h' })).toBe('Cerrar')
    expect(botonPedidoPestana(cierre('pestana'), { trabajando: true, estados: ['working'], huella: 'h' })).toBe('Cerrar igual')
    expect(botonPedidoPestana({ ...abrirBase, accion: 'cursor' })).toBe('Lanzar')
    expect(botonPedidoPestana(abrirBase)).toBe('Abrir')
  })
  it('texto trabajando por prioridad', () => {
    expect(textoTrabajando(['unknown', 'blocked'])).toBe('Está esperando un permiso')
    expect(textoTrabajando(['fondo', 'working'])).toBe('Está trabajando')
    expect(textoTrabajando(['fondo'])).toBe('Tiene trabajo en segundo plano')
    expect(textoTrabajando(['unknown'])).toBe('No sé si está trabajando')
  })
  it('conteo de cierre', () => {
    expect(conteoCierre({ ...cierreBase, sesiones: 1, terminales: 2 })).toBe('1 sesión de Claude · 2 terminales')
    expect(conteoCierre({ ...cierreBase, sesiones: 2, terminales: 0 })).toBe('2 sesiones de Claude')
    expect(conteoCierre({ ...cierreBase, sesiones: 0, terminales: 1 })).toBe('1 terminal')
    expect(conteoCierre({ ...cierreBase, sesiones: 0, terminales: 0 })).toBe('Vacía')
  })
  it('detalle de una línea', () => {
    expect(detallePedidoPestana(cierre('sesion'))).toBe('API')
    expect(detallePedidoPestana(cierre('pestana'))).toBe('API · 1 sesión de Claude · 2 terminales')
    expect(detallePedidoPestana({ ...abrirBase, accion: 'cursor', nombre: 'Renombres' })).toBe('Renombres')
    expect(detallePedidoPestana({ ...abrirBase, tarjeta: 'Nueva' })).toBe('Nueva')
    expect(detallePedidoPestana(abrirBase)).toBe('/home/usuario/proyecto')
    expect(
      detallePedidoPestana({
        ...abrirBase,
        accion: 'cerrar',
        terminal: { titulo: 'bash', proceso: '', cwd: '', estado: 'prompt', donde: '' },
      } as PedidoPestana),
    ).toBe('bash')
  })
})

describe('lib/pedidosPestana: dónde y aria de un cierre', () => {
  it('dónde muestra el espacio y el id del objetivo', () => {
    expect(dondeCierre({ ...cierreBase, workspace_label: 'Tienda', target_id: 'w2:t1' })).toBe('Tienda · w2:t1')
    expect(dondeCierre({ ...cierreBase, workspace_label: '', target_id: 'w2:t1' })).toBe('w2:t1')
  })
  it('aria del botón principal con artículo y "igual" al final', () => {
    const trab = { trabajando: true, estados: ['working'], huella: 'h' }
    expect(ariaAceptarPedidoPestana(cierre('pestana'))).toBe('Cerrar la pestaña')
    expect(ariaAceptarPedidoPestana(cierre('sesion'), trab)).toBe('Cerrar la sesión igual')
    expect(ariaAceptarPedidoPestana({ ...abrirBase, accion: 'cerrar' })).toBe('Cerrar la terminal')
    expect(ariaAceptarPedidoPestana({ ...abrirBase, accion: 'cursor' })).toBe('Lanzar el trabajador Cursor')
    expect(ariaAceptarPedidoPestana(abrirBase)).toBe('Abrir pestaña')
  })
  it('aria del No dice a qué', () => {
    expect(ariaRechazarPedidoPestana(cierre('tarjeta'))).toBe('No cerrar')
    expect(ariaRechazarPedidoPestana({ ...abrirBase, accion: 'cursor' })).toBe('No lanzar')
    expect(ariaRechazarPedidoPestana(abrirBase)).toBe('No abrir')
  })
})
