import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { execBody, handoffName, isExecutable, missingExecFields, parseOrigenes, parseTraspaso, splitPane, toTraspaso } from './traspaso'

const json = {
  origen: 'Imagenes ps9 (wF:p1)',
  destino_tipo: 'tab_nuevo',
  destino: 'Imagenes ps9 / tab nuevo',
  por_que: 'el hilo ya está largo',
  brief_path: '/tmp/brief.md',
  resumen_brief: 'Migrar CloudFront',
}
const block = (body: string, fence = '```') => `${fence}traspaso\n${body}\n${fence}`

describe('parseTraspaso', () => {
  it('returns the text untouched when there is no block', () => {
    const r = parseTraspaso('hola **che**')
    expect(r).toEqual({ before: 'hola **che**', after: '', traspaso: null, pending: false })
  })

  it('extracts the block and splits the surrounding text', () => {
    const text = `Te propongo esto:\n\n${block(JSON.stringify(json, null, 2))}\n\n¿Lo mando?`
    const r = parseTraspaso(text)
    expect(r.traspaso).toMatchObject({ origen: json.origen, destino_tipo: 'tab_nuevo', resumen_brief: 'Migrar CloudFront' })
    expect(r.before).toBe('Te propongo esto:')
    expect(r.after).toBe('¿Lo mando?')
    expect(r.pending).toBe(false)
  })

  it('accepts a block at the very start and with trailing info on the fence line', () => {
    const r = parseTraspaso('```traspaso json\n' + JSON.stringify(json) + '\n```')
    expect(r.traspaso?.destino).toBe(json.destino)
    expect(r.before).toBe('')
  })

  it('accepts tilde fences', () => {
    expect(parseTraspaso(block(JSON.stringify(json), '~~~')).traspaso).not.toBeNull()
  })

  it('shows the text as-is when the JSON is broken', () => {
    const text = `Mirá:\n${block('{"origen": "x", destino: }')}\nfin`
    const r = parseTraspaso(text)
    expect(r.traspaso).toBeNull()
    expect(r.before).toBe(text)
    expect(r.after).toBe('')
  })

  it('repairs trailing commas and smart quotes', () => {
    const r = parseTraspaso(block('{“origen”: “A (w1:p1)”, "destino": "B",}'))
    expect(r.traspaso).toMatchObject({ origen: 'A (w1:p1)', destino: 'B' })
  })

  it('rejects JSON without origen nor destino', () => {
    const text = block('{"foo": 1}')
    expect(parseTraspaso(text).traspaso).toBeNull()
    expect(parseTraspaso(text).before).toBe(text)
  })

  it('rejects non-object JSON', () => {
    expect(parseTraspaso(block('[1,2]')).traspaso).toBeNull()
    expect(parseTraspaso(block('"str"')).traspaso).toBeNull()
  })

  it('normalizes destino_tipo spellings and drops unknown ones', () => {
    expect(parseTraspaso(block('{"origen":"a","destino_tipo":"Workspace nuevo"}')).traspaso?.destino_tipo).toBe('workspace_nuevo')
    expect(parseTraspaso(block('{"origen":"a","destino_tipo":"Sesión existente"}')).traspaso?.destino_tipo).toBe('existente')
    expect(parseTraspaso(block('{"origen":"a","destino_tipo":"marte"}')).traspaso?.destino_tipo).toBeNull()
  })

  it('hides an unclosed block while streaming and flags it as pending', () => {
    const r = parseTraspaso('Va:\n```traspaso\n{"origen": "a', true)
    expect(r).toEqual({ before: 'Va:', after: '', traspaso: null, pending: true })
  })

  it('accepts an unclosed but valid block once the stream ended', () => {
    const r = parseTraspaso('Va:\n```traspaso\n' + JSON.stringify(json))
    expect(r.traspaso?.origen).toBe(json.origen)
  })

  it('leaves an unclosed broken block as plain text once the stream ended', () => {
    const text = 'Va:\n```traspaso\n{"origen": "a'
    expect(parseTraspaso(text)).toMatchObject({ before: text, traspaso: null, pending: false })
  })

  it('only takes the first block', () => {
    const text = `${block(JSON.stringify({ origen: 'uno' }))}\n${block(JSON.stringify({ origen: 'dos' }))}`
    const r = parseTraspaso(text)
    expect(r.traspaso?.origen).toBe('uno')
    expect(r.after).toContain('dos')
  })

  it('does not treat other code fences as traspaso', () => {
    const text = '```json\n{"origen":"a"}\n```'
    expect(parseTraspaso(text).traspaso).toBeNull()
  })
})

describe('campos de ejecución', () => {
  const full = {
    ...json,
    workspace_id: 'wF',
    label: 'CloudFront',
    cwd: '/home/usuario',
    agent_name: 'cloudfront',
    brief_path: '/home/usuario/.local/share/orquestador/handoffs/2026-10-31-x.md',
  }

  it('parsea los campos nuevos', () => {
    const t = parseTraspaso(block(JSON.stringify(full))).traspaso!
    expect(t).toMatchObject({ workspace_id: 'wF', label: 'CloudFront', cwd: '/home/usuario', agent_name: 'cloudfront', pane_id: '' })
  })

  it('tab_nuevo completo es ejecutable y el body omite vacíos', () => {
    const t = parseTraspaso(block(JSON.stringify(full))).traspaso!
    expect(missingExecFields(t)).toEqual([])
    const body = execBody(t)!
    expect(body.workspace_id).toBe('wF')
    expect('pane_id' in body).toBe(false)
  })

  it('detecta propuesta incompleta', () => {
    const t = parseTraspaso(block(JSON.stringify(json))).traspaso!
    expect(isExecutable(t)).toBe(false)
    expect(missingExecFields(t)).toEqual(['workspace_id', 'label', 'cwd', 'agent_name'])
    expect(execBody(t)).toBeNull()
  })

  it('existente solo pide pane_id; sin destino_tipo no es ejecutable', () => {
    const ex = parseTraspaso(block(JSON.stringify({ ...json, destino_tipo: 'existente', pane_id: 'wG:p1' }))).traspaso!
    expect(isExecutable(ex)).toBe(true)
    const none = parseTraspaso(block(JSON.stringify({ ...json, destino_tipo: 'otro' }))).traspaso!
    expect(missingExecFields(none)).toEqual(['destino_tipo'])
  })

  it('handoffName valida el basename', () => {
    expect(handoffName('/a/b/2026-10-31-x.md')).toBe('2026-10-31-x.md')
    expect(handoffName('/a/b/Bad Name.md')).toBeNull()
    expect(handoffName('/a/b/x.txt')).toBeNull()
  })
})

describe('origen con varias sesiones', () => {
  it('separa nombre e id de una sesión', () => {
    expect(splitPane('Imagenes ps9 (wF:p1)')).toEqual({ name: 'Imagenes ps9', pane: 'wF:p1' })
    expect(splitPane('Login federado')).toEqual({ name: 'Login federado', pane: '' })
    expect(splitPane('(wF:p1)')).toEqual({ name: '(wF:p1)', pane: '' })
  })

  it('parte la lista por comas sin cortar dentro de paréntesis', () => {
    expect(parseOrigenes('Modulo Acme PS9 (wC:p1), Artefacto Raro (wD:p1), Imagenes ps9 (wF:p1), Login federado (wG:p1)')).toEqual([
      { name: 'Modulo Acme PS9', pane: 'wC:p1' },
      { name: 'Artefacto Raro', pane: 'wD:p1' },
      { name: 'Imagenes ps9', pane: 'wF:p1' },
      { name: 'Login federado', pane: 'wG:p1' },
    ])
    expect(parseOrigenes('Uno (a, b), Dos')).toEqual([{ name: 'Uno', pane: 'a, b' }, { name: 'Dos', pane: '' }])
  })

  it('acepta "y" antes de la última y un origen solo', () => {
    expect(parseOrigenes('A (wC:p1), B (wD:p1) y C (wE:p1)').map((o) => o.name)).toEqual(['A', 'B', 'C'])
    expect(parseOrigenes('Imagenes ps9 (wF:p1)')).toEqual([{ name: 'Imagenes ps9', pane: 'wF:p1' }])
    expect(parseOrigenes('')).toEqual([])
  })

  it('un origen en forma de lista se une con comas', () => {
    expect(toTraspaso({ origen: ['A (wC:p1)', 'B (wD:p1)'], destino: 'X' })?.origen).toBe('A (wC:p1), B (wD:p1)')
  })
})

describe('origenes compartidos con el backend', () => {
  const casos: { origen: string; panes: string[] }[] = JSON.parse(
    readFileSync(new URL('../../../backend/tests/fixtures/origenes.json', import.meta.url).pathname, 'utf8'),
  )
  it.each(casos)('$origen', ({ origen, panes }) => {
    const got = [...new Set(parseOrigenes(origen).map((s) => s.pane).filter(Boolean))]
    expect(got).toEqual(panes)
  })
})
