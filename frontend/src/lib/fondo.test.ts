import { describe, expect, it } from 'vitest'
import { enSegundoPlano, estadoEfectivo, masFondo, mostrarMeta, rotuloTarea } from './fondo'
import type { Agent } from '../api/types'

const base = (status: Agent['status'], fondo: Agent['fondo'] = []): Agent => ({
  pane_id: 'p1',
  kind: 'claude',
  status,
  session_id: 's1',
  title: '',
  doing: '',
  pending: '',
  asks_user: false,
  last_activity: null,
  fondo,
})

describe('fondo', () => {
  it('solo idle o done con tareas cuentan como segundo plano', () => {
    const t = [{ id: '1', tipo: 'cursor' as const, texto: 'x', desde: 1 }]
    expect(enSegundoPlano(base('working', t))).toBe(false)
    expect(enSegundoPlano(base('idle', t))).toBe(true)
    expect(estadoEfectivo(base('done', t))).toBe('fondo')
  })

  it('rótulo y contador', () => {
    expect(rotuloTarea({ id: '1', tipo: 'agente', texto: 'auditoría', desde: 1 })).toBe('Un agente · auditoría')
    expect(masFondo(3)).toBe('+2')
    expect(masFondo(1)).toBe('')
  })
})

describe('mostrarMeta', () => {
  const nada = { unread: false, pide: false, pill: false, doing: false, mr: false, otroKind: false, fondo: false }
  it('no muestra la fila si no hay nada', () => {
    expect(mostrarMeta(nada)).toBe(false)
  })
  it('muestra la fila con una tarea en segundo plano aunque la píldora esté oculta', () => {
    expect(mostrarMeta({ ...nada, fondo: true })).toBe(true)
  })
  it('muestra la fila con cualquiera de los otros datos', () => {
    for (const k of ['unread', 'pide', 'pill', 'doing', 'mr', 'otroKind'] as const) expect(mostrarMeta({ ...nada, [k]: true })).toBe(true)
  })
})
