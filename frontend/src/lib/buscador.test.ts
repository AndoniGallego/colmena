import { describe, expect, it } from 'vitest'
import type { Aviso, Board, LibItem } from '../api/types'
import { aplanar, buscar, construirCatalogo, fuzzy, inicial, puntuar, recientesDe, saltoDeGrupo, sumarReciente, tramos, type Entrada } from './buscador'

const entrada = (id: string, titulo: string, over: Partial<Entrada> = {}): Entrada => ({
  id, grupo: 'sesion', titulo, sub: '', icono: 'pulse', claves: '', destino: { t: 'sesion', id }, ...over,
})

describe('fuzzy', () => {
  it('encuentra subsecuencias sin importar tildes ni mayúsculas', () => {
    expect(fuzzy('conversacion', 'Nueva Conversación')).not.toBeNull()
    expect(fuzzy('TSH', 'Trueshop')).not.toBeNull()
    expect(fuzzy('xyz', 'Trueshop')).toBeNull()
  })

  it('devuelve las posiciones de las letras que coinciden', () => {
    expect(fuzzy('tsh', 'Trueshop')!.marcas).toEqual([0, 4, 5])
    expect(fuzzy('bib', 'Biblioteca')!.marcas).toEqual([0, 1, 2])
  })

  it('las posiciones siguen al texto original aunque tenga tildes', () => {
    expect(fuzzy('ion', 'Acción')!.marcas).toEqual([3, 4, 5])
  })

  it('prefiere el inicio de palabra y las letras seguidas', () => {
    expect(fuzzy('ses', 'Sesión nueva')!.score).toBeGreaterThan(fuzzy('ses', 'Una cosa de pesos')!.score)
    expect(fuzzy('hor', 'Ver horarios')!.score).toBeGreaterThan(fuzzy('hor', 'Hacer otro rato')!.score)
  })

  it('una consulta vacía coincide con todo sin marcas', () => {
    expect(fuzzy('  ', 'lo que sea')).toEqual({ score: 0, marcas: [] })
  })

  it('no coincide si la consulta es más larga que el texto', () => {
    expect(fuzzy('abcdef', 'abc')).toBeNull()
  })
})

describe('puntuar y buscar', () => {
  it('exige todas las palabras, buscándolas también en el subtítulo y las claves', () => {
    const e = entrada('a', 'Deploy del módulo', { sub: 'Alfa · tab 2', claves: 'migración pendiente' })
    expect(puntuar('deploy alfa', e)).not.toBeNull()
    expect(puntuar('deploy migracion', e)).not.toBeNull()
    expect(puntuar('deploy beta', e)).toBeNull()
  })

  it('solo resalta el título', () => {
    const e = entrada('a', 'Deploy', { claves: 'zzz' })
    expect(puntuar('dep zzz', e)!.marcas).toEqual([0, 1, 2])
  })

  it('ordena por puntaje dentro del grupo y los grupos por su mejor resultado', () => {
    const cat = [
      entrada('s1', 'Revisión de pagos', { grupo: 'sesion' }),
      entrada('b1', 'Pagos', { grupo: 'biblioteca' }),
      entrada('s2', 'Pagos y stock', { grupo: 'sesion' }),
    ]
    const out = buscar('pagos', cat)
    expect(out.map((g) => g.grupo)).toEqual(['biblioteca', 'sesion'])
    expect(out[1].items.map((r) => r.entrada.id)).toEqual(['s2', 's1'])
  })

  it('limita los resultados por grupo', () => {
    const cat = Array.from({ length: 20 }, (_, i) => entrada(`s${i}`, `Sesión ${i}`))
    expect(aplanar(buscar('ses', cat, 5))).toHaveLength(5)
  })

  it('sin consulta mantiene el orden del catálogo', () => {
    const cat = [entrada('b', 'Bravo'), entrada('a', 'Alfa')]
    expect(aplanar(buscar('', cat)).map((r) => r.entrada.id)).toEqual(['b', 'a'])
  })
})

describe('saltoDeGrupo', () => {
  const cat = [entrada('a1', 'a'), entrada('a2', 'a'), entrada('b1', 'b', { grupo: 'aviso' }), entrada('c1', 'c', { grupo: 'biblioteca' })]
  const secs = buscar('', cat)

  it('salta al primer elemento del grupo siguiente y da la vuelta', () => {
    expect(saltoDeGrupo(secs, 0, 1)).toBe(2)
    expect(saltoDeGrupo(secs, 2, 1)).toBe(3)
    expect(saltoDeGrupo(secs, 3, 1)).toBe(0)
  })

  it('hacia atrás vuelve al inicio del grupo anterior', () => {
    expect(saltoDeGrupo(secs, 3, -1)).toBe(2)
    expect(saltoDeGrupo(secs, 0, -1)).toBe(3)
  })

  it('sin resultados queda en 0', () => {
    expect(saltoDeGrupo([], 0, 1)).toBe(0)
  })
})

describe('tramos', () => {
  it('parte el título en tramos marcados y sin marcar', () => {
    expect(tramos('Trueshop', [0, 4, 5])).toEqual([
      { t: 'T', on: true }, { t: 'rue', on: false }, { t: 'sh', on: true }, { t: 'op', on: false },
    ])
    expect(tramos('hola', [])).toEqual([{ t: 'hola', on: false }])
  })
})

describe('recientes', () => {
  it('suma al frente sin repetir y con tope', () => {
    expect(sumarReciente(['a', 'b'], 'b')).toEqual(['b', 'a'])
    expect(sumarReciente(['1', '2', '3', '4', '5', '6'], '7')).toEqual(['7', '1', '2', '3', '4', '5'])
  })

  it('descarta los que ya no existen y conserva el orden', () => {
    const cat = [entrada('a', 'A'), entrada('b', 'B')]
    expect(recientesDe(['b', 'zz', 'a'], cat).map((e) => [e.id, e.grupo])).toEqual([['b', 'reciente'], ['a', 'reciente']])
  })

  it('sin consulta muestra recientes y debajo secciones y acciones sin repetirlas', () => {
    const cat = construirCatalogo({ board: null, items: [], avisos: [], tema: 'dark' })
    const out = inicial(cat, ['sec:biblioteca'])
    expect(out[0].grupo).toBe('reciente')
    expect(out.flatMap((g) => g.items).filter((r) => r.entrada.id === 'sec:biblioteca')).toHaveLength(1)
    expect(out.map((g) => g.grupo)).toEqual(['reciente', 'ir', 'accion'])
  })
})

describe('catálogo', () => {
  const board = {
    updated_at: '', focused_tab_id: null, self_pane_id: null,
    workspaces: [
      {
        id: 'w1', number: 1, label: 'Imagenes ps9', status: 'working',
        tabs: [
          { id: 't1', label: 'infra', agents: [{ pane_id: 'p1', kind: 'claude', status: 'working', session_id: 's1', title: 'CloudFront', doing: 'editando', pending: '', asks_user: false, last_activity: null }], terminales: [{ pane_id: 'p9', terminal_id: 'x', titulo: 'logs', cwd: '/srv', proceso: 'tail', estado: 'corriendo', protegida: false }] },
          { id: 't2', label: 'theme', agents: [{ pane_id: 'p2', kind: 'claude', status: 'idle', session_id: null, title: 'Sin id', doing: '', pending: '', asks_user: false, last_activity: null }] },
        ],
      },
    ],
  } as unknown as Board
  const item = { id: 'l1', kind: 'diagrama', title: 'Diagrama de pago', session_titulo: 'Pagos', caption: '', description: '', project: '', nombre: 'f.json' } as LibItem
  const aviso = (id: number, over: Partial<Aviso>): Aviso => ({ id, ts: 1, kind: 'done', titulo: `n${id}`, cuerpo: '', session_id: '', pane_id: '', fecha: '', mr: '', tag: '', entregado: true, leido: false, motivo: '', ...over })
  const piezas = {
    secciones: [{ s: 'demo', titulo: 'Demo', sub: 'La sección de prueba', icono: 'calendar' as const, claves: 'prueba' }],
    acciones: [{ id: 'demo', titulo: 'Abrir demo', sub: 'Abre la demo', icono: 'calendar' as const, claves: 'prueba' }],
    avisos: [{ kind: 'demo', icono: 'calendar' as const, etiqueta: 'Demo' }],
  }
  const avisos = [aviso(1, { session_id: 's1' }), aviso(2, { kind: 'test' }), aviso(3, { kind: 'demo', fecha: '2026-11-02' })]
  const cat = construirCatalogo({ board, items: [item], avisos, tema: 'light', piezas })
  const por = (id: string) => cat.find((e) => e.id === id)

  it('sin piezas solo están las secciones y acciones del núcleo', () => {
    const solo = construirCatalogo({ board: null, items: [], avisos, tema: 'light' })
    expect(solo.filter((e) => e.grupo === 'ir').map((e) => e.titulo)).toEqual(['Tablero', 'Biblioteca', 'Ajustes'])
    expect(solo.filter((e) => e.grupo === 'accion').map((e) => e.titulo)).toEqual(['Cambiar tema'])
    expect(solo.find((e) => e.id === 'avi:3')).toBeUndefined()
  })

  it('las secciones de piezas van después del Tablero y sus acciones antes del tema', () => {
    expect(por('sec:demo')).toMatchObject({ titulo: 'Demo', icono: 'calendar', destino: { t: 'seccion', s: 'demo' } })
    expect(por('acc:demo')).toMatchObject({ titulo: 'Abrir demo', destino: { t: 'accion', a: 'demo' } })
    expect(por('avi:3')).toMatchObject({ sub: 'Demo', icono: 'calendar' })
  })

  it('incluye secciones, acciones, workspaces, tabs, sesiones, terminales, biblioteca y avisos con destino', () => {
    expect(cat.filter((e) => e.grupo === 'ir').map((e) => e.titulo)).toEqual(['Tablero', 'Demo', 'Biblioteca', 'Ajustes'])
    expect(cat.filter((e) => e.grupo === 'accion').map((e) => e.titulo)).toEqual(['Abrir demo', 'Cambiar tema'])
    expect(por('ws:w1')?.destino).toEqual({ t: 'pane', id: 'p1' })
    expect(por('tab:t2')?.destino).toEqual({ t: 'pane', id: 'p2' })
    expect(por('ses:s1')?.destino).toEqual({ t: 'sesion', id: 's1' })
    expect(por('ter:p9')?.destino).toEqual({ t: 'terminal', id: 'p9' })
    expect(por('lib:l1')?.destino).toEqual({ t: 'biblioteca', id: 'l1' })
    expect(por('avi:1')?.destino).toEqual({ t: 'aviso', id: 1 })
    expect(por('avi:3')).toBeDefined()
  })

  it('omite avisos sin destino y una sesión sin id cae al pane', () => {
    expect(por('avi:2')).toBeUndefined()
    expect(por('ses:p2')?.destino).toEqual({ t: 'pane', id: 'p2' })
  })

  it('el subtítulo del tema refleja el modo actual', () => {
    expect(por('acc:tema')?.sub).toBe('Pasar a oscuro')
  })

  it('ningún destino puede cerrar, escribir ni enviar: solo navegar o abrir', () => {
    const permitidos = new Set(['seccion', 'accion', 'sesion', 'terminal', 'pane', 'biblioteca', 'aviso'])
    expect(cat.every((e) => permitidos.has(e.destino.t))).toBe(true)
    expect(cat.filter((e) => e.destino.t === 'accion').map((e) => (e.destino as { a: string }).a).sort()).toEqual(['demo', 'tema'])
  })

  it('encuentra una sesión por lo que está haciendo', () => {
    const r = buscar('editando', cat)
    expect(aplanar(r)[0].entrada.id).toBe('ses:s1')
  })
})
