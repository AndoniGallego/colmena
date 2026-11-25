import { describe, expect, it } from 'vitest'
import { normalizeAvisos, normalizeBoard, normalizeLibItem, normalizeMessage, normalizeTerminalPreview, normalizeTranscript } from './normalize'

const ID = 'a'.repeat(32)
const SIG = 'B'.repeat(43)
const good = `https://h.ts.net:8445/v/${ID}/1893456000/${SIG}/`
const item = (src: string) => normalizeLibItem({ id: ID, kind: 'html', src })!

describe('src del visor', () => {
  it('acepta solo https bajo /v/ con token', () => {
    expect(item(good).src).toBe(good)
    for (const bad of [
      `http://h.ts.net:8445/v/${ID}/1893456000/${SIG}/`,
      `https://h.ts.net:8445/api/${ID}/1893456000/${SIG}/`,
      `javascript:alert(1)//v/${ID}/1893456000/${SIG}/`,
      `//h.ts.net/v/${ID}/1893456000/${SIG}/`,
      `/v/${ID}/1893456000/${SIG}/`,
      `${good}../x`,
      '',
    ]) expect(item(bad).src).toBe('')
  })
})

describe('normalizeMessage · turno automático de consulta', () => {
  it('no se muestra como algo que escribió el usuario', () => {
    expect(normalizeMessage({ id: 'c', role: 'user', text: '[Respuesta a tu consulta] ...', origen: 'consulta' })).toMatchObject({ role: 'event', text: 'Llegaron las respuestas de las sesiones' })
    expect(normalizeMessage({ id: 'u', role: 'user', text: 'hola', origen: 'escrito' })?.role).toBe('user')
  })
})

describe('normalizeMessage · marca del vigía', () => {
  it('conserva origen vigia y descarta cualquier otro', () => {
    expect(normalizeMessage({ id: 'v', role: 'assistant', text: 'x', origen: 'vigia' })?.origen).toBe('vigia')
    expect(normalizeMessage({ id: 'v', role: 'assistant', text: 'x', origen: 'otro' })?.origen).toBeUndefined()
    expect(normalizeMessage({ id: 'v', role: 'user', text: 'x', origen: 'vigia' })?.origen).toBeUndefined()
    const m = normalizeMessage({ id: 'v', role: 'assistant', text: 'x', origen: 'vigia', aviso: true, visto: true })
    expect([m?.aviso, m?.visto]).toEqual([true, true])
    expect(normalizeMessage({ id: 'v', role: 'assistant', text: 'x', aviso: true })?.aviso).toBeUndefined()
  })
})

describe('normalizeMessage · adjuntos de Centinela', () => {
  it('conserva solo ids válidos en mensajes del usuario', () => {
    const ok = '20261102-101010-captura.png'
    const m = normalizeMessage({ id: 'u', role: 'user', text: '', adjuntos: [ok, '../x.png', 3, '/etc/passwd'] })
    expect(m?.adjuntos).toEqual([ok])
    expect(normalizeMessage({ id: 'a', role: 'assistant', text: 'x', adjuntos: [ok] })).not.toHaveProperty('adjuntos')
    expect(normalizeMessage({ id: 'u', role: 'user', text: 'x', adjuntos: 'nope' })).not.toHaveProperty('adjuntos')
    const many = Array.from({ length: 8 }, (_, i) => `20261102-10101${i}-a.png`)
    expect(normalizeMessage({ id: 'u', role: 'user', text: 'x', adjuntos: many })?.adjuntos).toHaveLength(5)
  })
})

describe('normalizeBoard', () => {
  it('normaliza el estado de las terminales y los conflictos', () => {
    expect(normalizeBoard({ workspaces: [] }).terminales).toBe('ok')
    expect(normalizeBoard({ workspaces: [], terminales: 'sin_conexion' }).terminales).toBe('sin_conexion')
    expect(normalizeBoard({ workspaces: [], conflictos: ['g7:t1', 3] }).conflictos).toEqual(['g7:t1'])
  })

  it('normaliza caidos como lista de strings acotada', () => {
    expect(normalizeBoard({ workspaces: [] }).caidos).toEqual([])
    expect(normalizeBoard({ workspaces: [], caidos: ['guardian', 1, 'otro'] }).caidos).toEqual(['guardian', 'otro'])
    expect(normalizeBoard({ workspaces: [], caidos: Array.from({ length: 25 }, (_, i) => `x${i}`) }).caidos).toHaveLength(20)
  })
})

describe('normalizeBoard · pendiente', () => {
  const tab = (a: object) => ({ workspaces: [{ id: 'w1', number: 1, tabs: [{ id: 't', label: 'x', agents: [a] }] }] })
  it('conserva pendiente y por defecto es false', () => {
    const si = normalizeBoard(tab({ pane_id: 'p', asks_user: false, pendiente: true })).workspaces[0]!.tabs[0]!.agents[0]!
    expect(si.pendiente).toBe(true)
    const no = normalizeBoard(tab({ pane_id: 'p' })).workspaces[0]!.tabs[0]!.agents[0]!
    expect(no.pendiente).toBe(false)
  })
})

describe('reportes', () => {
  it('normaliza un reporte con filas y tope de 8', () => {
    const items = Array.from({ length: 10 }, (_, i) => ({ session_id: `s${i}`, nombre: `S${i}`, quedo: 'ok', cadena: i === 0 }))
    const m = normalizeMessage({ id: 'r1', role: 'reporte', text: 'x', items: [...items, { nombre: 'sin id' }], mas: 3 })!
    expect(m.role).toBe('reporte')
    expect(m.items).toHaveLength(8)
    expect(m.items![0].cadena).toBe(true)
    expect(m.items![1].pregunta).toBe('')
    expect(m.mas).toBe(3)
  })

  it('el evento de respuesta conserva la sesión', () => {
    const m = normalizeMessage({ role: 'event', kind: 'respuesta', session_id: 's1', text: 'Le contestaste a X: sí' })!
    expect(m.kind).toBe('respuesta')
    expect(m.session_id).toBe('s1')
  })
})

describe('normalizeAvisos', () => {
  it('conserva avisos de progreso', () => {
    const out = normalizeAvisos({
      items: [{ id: 1, ts: 1, kind: 'progreso', titulo: 'Viene avanzando', cuerpo: 'Va bien', tag: 'progreso-enc-1' }],
    })
    expect(out.items).toHaveLength(1)
    expect(out.items[0]).toMatchObject({ kind: 'progreso', tag: 'progreso-enc-1' })
  })
})

describe('normalizeAvisos entorno', () => {
  it('conserva los avisos de entornos con su tag', () => {
    const out = normalizeAvisos({ items: [{ id: 1, ts: 1, kind: 'entorno', titulo: 'Entornos', cuerpo: 'Se cayó hs-api (hybrid-search)', tag: 'entorno-hybrid-search:hs-api' }] })
    expect(out.items).toHaveLength(1)
    expect(out.items[0]?.kind).toBe('entorno')
    expect(out.items[0]?.tag).toBe('entorno-hybrid-search:hs-api')
  })
})

describe('ítems de pruebas', () => {
  it('conserva el informe y las evidencias', () => {
    const it = normalizeLibItem({ id: ID, kind: 'pruebas', pruebas_raw: '{"titulo":"T"}', evidencias: { '/a.png': ID, '/b.png': 3 } })!
    expect(it.kind).toBe('pruebas')
    expect(it.pruebas_raw).toBe('{"titulo":"T"}')
    expect(it.evidencias).toEqual({ '/a.png': ID })
  })
  it('sin informe queda vacío', () => {
    const it = normalizeLibItem({ id: ID, kind: 'pruebas' })!
    expect(it.pruebas_raw).toBe('')
    expect(it.evidencias).toEqual({})
  })
})

describe('normalizeTranscript con bloques comando', () => {
  it('deja pasar cmid y cstart de los mensajes de Claude', () => {
    const page = normalizeTranscript({ items: [
      { kind: 'claude', text: 'x', ts: '', cmid: 'mid-aaaaaaaa', cstart: 2 },
      { kind: 'claude', text: 'y', ts: '', cmid: 5, cstart: 'no' },
    ] })
    expect(page.items[0]).toMatchObject({ cmid: 'mid-aaaaaaaa', cstart: 2 })
    expect(page.items[1].cmid).toBeUndefined()
  })
  it('deja pasar el cwd real (ccwd) solo si es una ruta absoluta', () => {
    const page = normalizeTranscript({ items: [
      { kind: 'claude', text: 'x', ts: '', cmid: 'mid-aaaaaaaa', cstart: 0, ccwd: '/srv/app' },
      { kind: 'claude', text: 'y', ts: '', cmid: 'mid-bbbbbbbb', cstart: 0, ccwd: 'rel' },
    ] })
    expect(page.items[0].ccwd).toBe('/srv/app')
    expect(page.items[1].ccwd).toBeUndefined()
  })
})

describe('normalizePedidosPestana: pedido para cerrar una terminal', () => {
  const base = { id: '550e8400-e29b-41d4-a716-446655440000', carpeta: '', mensaje: '', origen: { pane_id: 'w1:p1', nombre: 'S' }, ts: 1, vence: 2 }

  it('conserva la acción y la terminal', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    const [p] = normalizePedidosPestana([{ ...base, accion: 'cerrar', terminal: { pane_id: 'w2:p1', titulo: 'logs', cwd: '~/x', proceso: 'tail', estado: 'corriendo', donde: 'A / B' } }])
    expect(p.accion).toBe('cerrar')
    expect(p.terminal).toEqual({ pane_id: 'w2:p1', titulo: 'logs', cwd: '~/x', proceso: 'tail', estado: 'corriendo', donde: 'A / B' })
  })

  it('una acción desconocida o sin terminal se descarta', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    expect(normalizePedidosPestana([{ ...base, accion: 'borrar', terminal: { pane_id: 'w2:p1' } }])).toEqual([])
    expect(normalizePedidosPestana([{ ...base, accion: 'cerrar' }])).toEqual([])
  })
})

describe('normalizeTerminalPreview: qué se lleva el cierre', () => {
  it('respeta lo que dice el servidor', () => {
    expect(normalizeTerminalPreview({ cierra: 'terminal' }).cierra).toBe('terminal')
    expect(normalizeTerminalPreview({ cierra: 'espacio' }).cierra).toBe('espacio')
  })
  it('sin el dato, supone que se lleva la pestaña (así siempre se confirma)', () => {
    expect(normalizeTerminalPreview({}).cierra).toBe('pestana')
    expect(normalizeTerminalPreview({ cierra: 'raro' }).cierra).toBe('pestana')
  })
})

describe('normalizePedidosPestana: pedido de trabajador Cursor', () => {
  const base = { id: '550e8400-e29b-41d4-a716-446655440000', carpeta: '/home/u/repo', mensaje: 'Renombrá foo', nombre: 'Renombrar', origen: { pane_id: 'w1:p1', nombre: 'S' }, ts: 1, vence: 2, accion: 'cursor' }

  it('conserva acción, nombre, pedido y modelo; descarta pestañas, terminal y tarjeta', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    const [p] = normalizePedidosPestana([{ ...base, cursor: { modelo: 'composer-2.5-fast' }, tarjeta: 'T', terminal: { pane_id: 'w2:p1' }, pestanas: [{ nombre: 'x', tipo: 'claude', carpeta: '/x', mensaje: 'hola' }] }])
    expect(p.accion).toBe('cursor')
    expect(p.nombre).toBe('Renombrar')
    expect(p.mensaje).toBe('Renombrá foo')
    expect(p.cursor).toEqual({ modelo: 'composer-2.5-fast' })
    expect(p.pestanas).toBeUndefined()
    expect(p.terminal).toBeUndefined()
    expect(p.tarjeta).toBeUndefined()
    const [sin] = normalizePedidosPestana([base])
    expect(sin.cursor).toEqual({})
  })

  it('sin pedido, sin nombre o sin carpeta no se muestra', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    expect(normalizePedidosPestana([{ ...base, mensaje: '   ' }])).toEqual([])
    expect(normalizePedidosPestana([{ ...base, nombre: '' }])).toEqual([])
    expect(normalizePedidosPestana([{ ...base, carpeta: '' }])).toEqual([])
  })

  it('un modelo que el backend no aceptaría descarta el pedido', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    for (const modelo of ['--yolo', '-m', 'a b', 'x;rm', 'm'.repeat(81), 3, 'gpt/5']) {
      expect(normalizePedidosPestana([{ ...base, cursor: { modelo } }])).toEqual([])
    }
    expect(normalizePedidosPestana([{ ...base, cursor: { modelo: 'gpt-5.2[high]' } }])[0].cursor).toEqual({ modelo: 'gpt-5.2[high]' })
  })

  it('cualquier otra acción sigue sin mostrarse', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    expect(normalizePedidosPestana([{ ...base, accion: 'cursores' }])).toEqual([])
  })
})

describe('normalizePedidosPestana: pedidos de cierre y session_id', () => {
  const base = { id: '550e8400-e29b-41d4-a716-446655440000', carpeta: '', mensaje: '', origen: { pane_id: 'w1:p1', nombre: 'S' }, ts: 1, vence: 2 }

  it('el origen trae session_id', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    const [p] = normalizePedidosPestana([{ ...base, origen: { pane_id: 'w1:p1', nombre: 'A', session_id: 's1' } }])
    expect(p.origen.session_id).toBe('s1')
    expect(normalizePedidosPestana([base])[0].origen.session_id).toBe('')
  })

  it('normaliza un pedido de cerrar pestaña', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    const [p] = normalizePedidosPestana([{ ...base, accion: 'cerrar', cierre: { objetivo: 'pestana', tipo: 'tab', target_id: 'w2:t1', label: 'vacío', workspace_label: 'Dos', carpeta: '/tmp', sesiones: 1, terminales: -2 } }])
    expect(p.accion).toBe('cerrar')
    expect(p.cierre).toEqual({ objetivo: 'pestana', tipo: 'tab', target_id: 'w2:t1', label: 'vacío', workspace_label: 'Dos', carpeta: '/tmp', sesiones: 1, terminales: 0 })
    expect(p.terminal).toBeUndefined()
  })

  it('descarta un cierre con objetivo o target inválido', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    expect(normalizePedidosPestana([{ ...base, accion: 'cerrar', cierre: { objetivo: 'todo', tipo: 'tab', target_id: 'w2:t1' } }])).toEqual([])
    expect(normalizePedidosPestana([{ ...base, accion: 'cerrar', cierre: { objetivo: 'pestana', tipo: 'tab', target_id: '' } }])).toEqual([])
  })

  it('normaliza la vista de cierre', async () => {
    const { normalizeVistaCierrePedido } = await import('./normalize')
    expect(normalizeVistaCierrePedido({ trabajando: true, estados: ['working', 3], huella: 'h' })).toEqual({ trabajando: true, estados: ['working'], huella: 'h' })
    expect(normalizeVistaCierrePedido({ trabajando: true })).toBeNull()
  })
})

describe('uso de hoy en el tablero', () => {
  it('conserva el uso de la sesión y descarta lo que no es un número', () => {
    const board = normalizeBoard({
      workspaces: [{ id: 'w1', tabs: [{ id: 't1', agents: [
        { pane_id: 'w1:p1', status: 'working', uso: { total: 312000, usd: 4.1 } },
        { pane_id: 'w1:p2', status: 'working', uso: { total: 900, usd: null } },
        { pane_id: 'w1:p3', status: 'working', uso: { total: 'x', usd: 2 } },
        { pane_id: 'w1:p4', status: 'working' },
      ] }] }],
    })
    const agents = board.workspaces[0].tabs[0].agents
    expect(agents[0].uso).toEqual({ total: 312000, usd: 4.1 })
    expect(agents[1].uso).toEqual({ total: 900, usd: null })
    expect(agents[2].uso).toBeNull()
    expect(agents[3].uso).toBeNull()
  })
})

describe('normalizePedidosPestana: acciones del MCP y lectura previa', () => {
  const base = { id: '550e8400-e29b-41d4-a716-446655440000', carpeta: '', mensaje: 'hola', origen: { pane_id: 'w1:p1', nombre: 'S' }, ts: 1, vence: 2 }

  it('conserva mensaje, programada y tarea con sus datos', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    const [m, p, t] = normalizePedidosPestana([
      { ...base, accion: 'mensaje', envio: { pane_id: 'w2:p1', nombre: 'Dos', texto: 'x' } },
      { ...base, accion: 'programada', programada: { cuando: '09:30', pane_id: 'w1:p1', nombre: 'S' } },
      { ...base, carpeta: '/r', accion: 'tarea', tarea: { ticket: 'SITE-12' } },
    ])
    expect(m.accion).toBe('mensaje')
    expect(m.envio).toEqual({ pane_id: 'w2:p1', nombre: 'Dos' })
    expect(p.programada).toEqual({ cuando: '09:30', pane_id: 'w1:p1', nombre: 'S' })
    expect(t.tarea).toEqual({ ticket: 'SITE-12' })
  })

  it('sin los datos de su acción se descartan', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    expect(normalizePedidosPestana([
      { ...base, accion: 'mensaje' },
      { ...base, accion: 'programada', programada: { pane_id: 'w1:p1' } },
      { ...base, accion: 'tarea', tarea: {} },
    ])).toEqual([])
  })

  it('conserva leyo_otra_sesion solo si es válido', async () => {
    const { normalizePedidosPestana } = await import('./normalize')
    const [a, b] = normalizePedidosPestana([
      { ...base, leyo_otra_sesion: { nombre: 'Pagos', ts: 5 } },
      { ...base, leyo_otra_sesion: { nombre: '', ts: 'x' } },
    ])
    expect(a.leyo_otra_sesion).toEqual({ nombre: 'Pagos', ts: 5 })
    expect(b.leyo_otra_sesion).toBeUndefined()
  })

  it('el evento descartado se acepta (el pedido sale de la lista)', async () => {
    const { normalizePedidoPestanaEvento } = await import('./normalize')
    expect(normalizePedidoPestanaEvento({ id: base.id, estado: 'descartado' })).toEqual({ id: base.id, estado: 'descartado' })
  })
})
