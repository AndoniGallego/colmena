import { describe, expect, it } from 'vitest'
import { closeBody, missingFields, soloUnknown, paneLine, parseCerrar, protectedTabClosable, resumeCommand, targetLine, unsafeCwd } from './cerrar'
import type { Tab, Terminal, Workspace } from '../api/types'
import { parseTraspaso } from './traspaso'

const json = { id: '0b6f1c1e-4a55-4e1d-9d33-1f3c2a7d9e10', tipo: 'tab', target_id: 'w3:t2', destino: 'Logout federado (w3:t2)', por_que: 'terminó' }
const block = (body: string) => '```cerrar\n' + body + '\n```'

describe('parseCerrar', () => {
  it('devuelve el texto tal cual sin bloque', () => {
    expect(parseCerrar('hola')).toEqual({ before: 'hola', after: '', cerrar: null, pending: false })
  })

  it('extrae el bloque y separa el texto', () => {
    const r = parseCerrar(`Dale:\n\n${block(JSON.stringify(json))}\n\n¿Lo cierro?`)
    expect(r.cerrar).toEqual(json)
    expect(r.before).toBe('Dale:')
    expect(r.after).toBe('¿Lo cierro?')
  })

  it('con JSON roto queda como código', () => {
    const text = block('{no es json')
    const r = parseCerrar(text)
    expect(r.cerrar).toBeNull()
    expect(r.before).toBe(text)
  })

  it('marca pendiente mientras llega en streaming', () => {
    expect(parseCerrar('Ok\n```cerrar\n{"id"', true)).toMatchObject({ pending: true, cerrar: null, before: 'Ok' })
  })

  it('normaliza el tipo y acepta porque sin guion bajo', () => {
    const r = parseCerrar(block(JSON.stringify({ ...json, tipo: 'Workspace', por_que: undefined, porque: 'x' })))
    expect(r.cerrar).toMatchObject({ tipo: 'workspace', por_que: 'x' })
  })

  it('bloques responder o aprobar no son cards', () => {
    for (const lang of ['responder', 'aprobar']) {
      const text = '```' + lang + '\n' + JSON.stringify(json) + '\n```'
      expect(parseCerrar(text).cerrar).toBeNull()
      expect(parseTraspaso(text).traspaso).toBeNull()
    }
  })
})

describe('missingFields', () => {
  it('completa no falta nada', () => {
    expect(missingFields(parseCerrar(block(JSON.stringify(json))).cerrar!)).toEqual([])
  })

  it('detecta id, tipo y target inválidos', () => {
    const c = parseCerrar(block(JSON.stringify({ destino: 'algo', id: 'corto', target_id: '--evil' }))).cerrar!
    expect(missingFields(c)).toEqual(['id', 'tipo', 'target_id'])
  })
})

describe('closeBody', () => {
  it('arma el cuerpo del servidor', () => {
    expect(closeBody({ id: 'abc12345', tipo: 'tab', targetId: 'w1:t1', huella: 'h', origen: 'jefe', destino: 'D', porQue: 'P' })).toEqual({
      id: 'abc12345', tipo: 'tab', target_id: 'w1:t1', huella: 'h', origen: 'jefe', destino: 'D', por_que: 'P',
    })
  })
})

describe('forzar', () => {
  it('closeBody manda forzar solo si se pidió', () => {
    const base = { id: 'abc12345', tipo: 'tab' as const, targetId: 'w1:t1', huella: 'h', origen: 'manual' as const, destino: 'D', porQue: 'P' }
    expect(closeBody({ ...base, forzar: true })).toMatchObject({ forzar: true })
    expect(closeBody(base)).not.toHaveProperty('forzar')
  })

  it('soloUnknown: hay bloqueantes y todos son "no sé"', () => {
    expect(soloUnknown([{ pane_id: 'a', status: 'unknown' }])).toBe(true)
    expect(soloUnknown([{ pane_id: 'a', status: 'unknown' }, { pane_id: 'b', status: 'working' }])).toBe(false)
    expect(soloUnknown([])).toBe(false)
  })
})

describe('resumeCommand', () => {
  const sid = '11111111-2222-3333-4444-555555555555'
  it('arma cd + claude --resume con la ruta entre comillas', () => {
    expect(resumeCommand({ session_id: sid, cwd: "/home/usuario/it's here", titulo: '' })).toBe(`cd -- '/home/usuario/it'\\''s here' && claude --resume ${sid}`)
  })

  it('sin ruta usa solo claude --resume y rechaza ids raros', () => {
    expect(resumeCommand({ session_id: sid, cwd: '', titulo: '' })).toBe(`claude --resume ${sid}`)
    expect(resumeCommand({ session_id: 'x; rm -rf /', cwd: '', titulo: '' })).toBeNull()
    expect(resumeCommand({ session_id: null, cwd: '', titulo: '' })).toBeNull()
  })

  it('no ofrece comando con caracteres de control ni bidi en la ruta', () => {
    for (const cwd of ['/a\nrm -rf', '/a\u0085b', '/a\u202eb', '/a\u2067b', '/a\x7fb']) {
      expect(resumeCommand({ session_id: sid, cwd, titulo: '' })).toBeNull()
      expect(unsafeCwd({ session_id: sid, cwd, titulo: '' })).toBe(true)
    }
    expect(unsafeCwd({ session_id: sid, cwd: '/ok', titulo: '' })).toBe(false)
  })
})

describe('paneLine', () => {
  it('Claude con título y terminal con proceso', () => {
    expect(paneLine({ pane_id: 'p', kind: 'claude', status: 'idle', titulo: 'Arreglando el login', session_id: null, cwd: '', proceso: null })).toEqual({ who: 'Claude', what: 'Arreglando el login' })
    expect(paneLine({ pane_id: 'p', kind: null, status: null, titulo: '', session_id: null, cwd: '', proceso: 'node' })).toEqual({ who: 'Terminal', what: 'node' })
  })
})

describe('targetLine', () => {
  const base = { tipo: 'tab' as const, target_id: 'w3:t2', label: '1', workspace_label: 'Login', cierra_workspace: false, tab_count: 1, panes: [], bloqueantes: [], huella: 'h' }
  it('muestra workspace, tab e id del servidor', () => {
    expect(targetLine(base)).toBe('Workspace Login · tab 1 (w3:t2)')
    expect(targetLine({ ...base, tipo: 'workspace', target_id: 'w3', label: 'Login' })).toBe('Workspace Login (w3)')
  })
  it('sin label cae al id, nunca a lo que dijo Centinela', () => {
    expect(targetLine({ ...base, label: '', workspace_label: 'Login' })).toBe('Workspace Login · tab w3:t2 (w3:t2)')
    expect(targetLine({ ...base, tipo: 'workspace', target_id: 'w3', label: '', workspace_label: '' })).toBe('Workspace w3 (w3)')
  })
})

describe('protectedTabClosable', () => {
  const term = (proceso: string): Terminal => ({ pane_id: 'w1:p2', terminal_id: 't', titulo: '', cwd: '', proceso, estado: 'prompt', protegida: false })
  const tab = (id: string, terminales: Terminal[], agents = 0): Tab => ({
    id,
    label: id,
    agents: Array.from({ length: agents }, () => ({ pane_id: `${id}:a`, kind: 'claude', status: 'idle' }) as unknown as Tab['agents'][number]),
    terminales,
  })
  const ws = (tabs: Tab[], pinned = true): Workspace => ({ id: 'w1', number: 1, label: 'Super orquestador', pinned, status: 'idle', tabs })

  it('offers a terminal-only tab of the protected workspace', () => {
    const t = tab('w1:t2', [term('bash'), term('node')])
    expect(protectedTabClosable(ws([tab('w1:t1', [], 1), t]), t)).toBe(true)
  })
  it('never offers a tab with Claude, marked or by process', () => {
    const marked = tab('w1:t2', [term('bash')], 1)
    const byProcess = tab('w1:t3', [term('bash'), term('claude')])
    const w = ws([tab('w1:t1', [], 1), marked, byProcess])
    expect(protectedTabClosable(w, marked)).toBe(false)
    expect(protectedTabClosable(w, byProcess)).toBe(false)
  })
  it('never offers the last tab, an empty tab, or a tab outside a protected workspace', () => {
    const only = tab('w1:t2', [term('bash')])
    expect(protectedTabClosable(ws([only]), only)).toBe(false)
    const empty = tab('w1:t3', [])
    expect(protectedTabClosable(ws([only, empty]), empty)).toBe(false)
    expect(protectedTabClosable(ws([only, empty], false), only)).toBe(false)
  })
})
