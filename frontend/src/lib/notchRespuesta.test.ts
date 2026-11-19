import { describe, expect, it } from 'vitest'
import type { DialogView, PedidoPermiso } from '../api/types'
import { normalizeDialog } from './dialogo'
import type { PreguntaSesion } from '../api/types'
import type { PedidoPestana } from '../api/types'
import { formaPedido, formaRespuesta, resumenEntrada } from './notchRespuesta'

const pedido: PedidoPermiso = {
  id: 'p1',
  session_id: 's1',
  pane_id: 'w1:p1',
  herramienta: 'Bash',
  entrada: { command: 'ls' },
  estado: 'abierto',
  regla: { herramienta: 'Bash', contenido: 'ls:*', archivo: '/x.json', huella: 'h' },
}

describe('formaRespuesta', () => {
  it('pregunta del diálogo simple con otro', () => {
    const view: DialogView = normalizeDialog({
      tipo: 'pregunta',
      huella: 'h1',
      pane_id: 'p1',
      pregunta: {
        preguntas: [
          {
            header: '',
            texto: '¿Seguimos?',
            multi: false,
            otro: true,
            opciones: [{ label: 'Sí' }, { label: 'No' }],
          },
        ],
      },
    })
    expect(formaRespuesta(view, false)).toEqual({
      tipo: 'opciones',
      pregunta: '¿Seguimos?',
      opciones: ['Sí', 'No'],
      otro: true,
      via: 'dialogo',
    })
  })

  it('pregunta múltiple del diálogo manda a Colmena', () => {
    const view: DialogView = normalizeDialog({
      tipo: 'pregunta',
      huella: 'h1',
      pane_id: 'p1',
      pregunta: {
        preguntas: [
          { header: '', texto: 'A', multi: true, opciones: [{ label: '1' }, { label: '2' }] },
          { header: '', texto: 'B', multi: true, opciones: [{ label: '3' }, { label: '4' }] },
        ],
      },
    })
    expect(formaRespuesta(view, false)).toEqual({ tipo: 'abrir', motivo: 'Contestala en Colmena' })
  })

  it('permiso incompleto solo deja rechazar', () => {
    const view: DialogView = normalizeDialog({
      tipo: 'permiso',
      huella: 'h1',
      pane_id: 'p1',
      permiso: {
        herramienta: 'Bash',
        detalle: 'npm test',
        descripcion: '',
        completo: false,
        opciones: ['si', 'si_siempre', 'no'],
        regla: null,
        mas_en_terminal: false,
      },
    })
    const f = formaRespuesta(view, false)
    expect(f.tipo).toBe('permiso')
    if (f.tipo === 'permiso') expect(f.puedePermitir).toBe(false)
  })

  it('pedido por gancho usa el id del pedido', () => {
    const view: DialogView = { tipo: 'pedido', pedido }
    expect(formaRespuesta(view, false)).toEqual({
      tipo: 'permiso',
      titulo: 'Bash',
      detalle: 'ls',
      puedePermitir: true,
      via: 'pedido',
      pedidoId: 'p1',
    })
  })

  it('ninguna forma ofrece siempre', () => {
    const permisoView: DialogView = normalizeDialog({
      tipo: 'permiso',
      huella: 'h1',
      pane_id: 'p1',
      permiso: {
        herramienta: 'Bash',
        detalle: 'ls',
        descripcion: '',
        completo: true,
        opciones: ['si', 'si_siempre', 'no'],
        regla: 'ls *',
        mas_en_terminal: false,
      },
    })
    const todas: ReturnType<typeof formaRespuesta>[] = [
      formaRespuesta(permisoView, false),
      formaRespuesta({ tipo: 'pedido', pedido }, false),
      formaRespuesta(null, true),
      formaRespuesta(null, false),
    ]
    for (const f of todas) expect(JSON.stringify(f)).not.toMatch(/siempre/i)
  })
})

describe('resumenEntrada', () => {
  it('prefiere command', () => {
    expect(resumenEntrada({ ...pedido, entrada: { command: 'ls' } })).toBe('ls')
  })
})

describe('formaRespuesta con pregunta de sesión', () => {
  const ps = (preguntas: PreguntaSesion['preguntas']): PreguntaSesion => ({
    sig: 's:1',
    session_id: 's1',
    pane_id: 'w1:p1',
    nombre: 'Uno',
    preguntas,
  })
  const op = (label: string) => ({ label, detalle: '', recomendada: false })

  it('una pregunta con opciones da opciones con otro', () => {
    expect(formaRespuesta(null, false, ps([{ pregunta: '¿Cómo?', opciones: [op('A'), op('B')] }]))).toEqual({
      tipo: 'opciones',
      pregunta: '¿Cómo?',
      opciones: ['A', 'B'],
      otro: true,
      via: 'sesion',
    })
  })

  it('una pregunta sin opciones manda a abrir', () => {
    expect(formaRespuesta(null, false, ps([{ pregunta: '¿Cómo?', opciones: [] }]))).toEqual({
      tipo: 'abrir',
      motivo: 'Contestala en Colmena',
    })
  })

  it('varias preguntas mandan a abrir', () => {
    const q = { pregunta: 'x', opciones: [op('A')] }
    expect(formaRespuesta(null, false, ps([q, q, q]))).toEqual({ tipo: 'abrir', motivo: 'Tiene 3 preguntas' })
  })

  it('sin pregunta cargada y cargando muestra cargando', () => {
    expect(formaRespuesta(null, true, null)).toEqual({ tipo: 'cargando' })
  })
})

const pedidoCierre = (objetivo: 'sesion' | 'pestana'): PedidoPestana => ({
  id: '550e8400-e29b-41d4-a716-446655440000',
  carpeta: '/home/usuario/proyecto',
  mensaje: '',
  accion: 'cerrar',
  cierre: {
    objetivo,
    tipo: 'tab',
    target_id: 'w1:t1',
    label: 'API',
    workspace_label: 'Tienda',
    carpeta: '/home/usuario/proyecto',
    sesiones: 1,
    terminales: 0,
  },
  origen: { pane_id: 'w1:p1', nombre: 'Origen', session_id: 's1' },
  ts: 1,
  vence: 2,
})

describe('formaPedido', () => {
  it('forma pedido de un cierre trabajando', () => {
    expect(
      formaPedido(pedidoCierre('pestana'), { vista: { trabajando: true, estados: ['working'], huella: 'h' } }),
    ).toMatchObject({ tipo: 'pedido', titulo: 'Cerrar pestaña', boton: 'Cerrar igual', aviso: 'Está trabajando' })
  })
  it('sin vista o sin trabajar no hay aviso y el botón es Cerrar', () => {
    expect(formaPedido(pedidoCierre('sesion'))).toMatchObject({
      tipo: 'pedido',
      pedidoId: '550e8400-e29b-41d4-a716-446655440000',
      boton: 'Cerrar',
      aviso: '',
      enviando: false,
      error: '',
    })
    expect(
      formaPedido(pedidoCierre('sesion'), { vista: { trabajando: false, estados: ['idle'], huella: 'h' } }).tipo,
    ).toBe('pedido')
  })
  it('trae dónde (espacio e id) y los aria de los botones', () => {
    expect(formaPedido(pedidoCierre('pestana'), { vista: { trabajando: true, estados: ['working'], huella: 'h' } })).toMatchObject({
      donde: 'Tienda · w1:t1',
      ariaAceptar: 'Cerrar la pestaña igual',
      ariaRechazar: 'No cerrar',
    })
  })
  it('refleja enviando y error', () => {
    expect(formaPedido(pedidoCierre('sesion'), { enviando: true, error: 'x' })).toMatchObject({ enviando: true, error: 'x' })
  })
})
