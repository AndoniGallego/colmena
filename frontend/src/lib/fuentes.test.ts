import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { citaRef, esMemoria, fechaCorta, lugares, pasoMemoria, resumenIndice, splitFuentes, toFuentes } from './fuentes'

const indexHtml = readFileSync(new URL('../../index.html', import.meta.url).pathname, 'utf8')
const mainTs = readFileSync(new URL('../main.ts', import.meta.url).pathname, 'utf8')

describe('tipografía local (sin Google Fonts)', () => {
  it('index.html no referencia fonts.googleapis ni fonts.gstatic', () => {
    expect(indexHtml).not.toMatch(/fonts\.googleapis/)
    expect(indexHtml).not.toMatch(/fonts\.gstatic/)
  })

  it('main.ts importa las tres familias @fontsource-variable', () => {
    expect(mainTs).toMatch(/@fontsource-variable\/bricolage-grotesque/)
    expect(mainTs).toMatch(/@fontsource-variable\/instrument-sans/)
    expect(mainTs).toMatch(/@fontsource-variable\/jetbrains-mono/)
  })
})

const SID = 'aaaaaaaa-1111-2222-3333-444444444444'
const bloque = (body: string) => `Lo levantamos con el override.\n\n\`\`\`fuentes\n${body}\n\`\`\``

describe('toFuentes', () => {
  it('acepta sesiones y engram válidos y descarta el resto', () => {
    const { items } = toFuentes([
      { tipo: 'sesion', session_id: SID, turno: 128, titulo: 'Entorno local Tienda', fecha: '2026-10-01' },
      { tipo: 'engram', id: 412, titulo: 'Docker sin egress', fecha: '2026-09-18', proyecto: 'acme' },
      { tipo: 'sesion', session_id: '../etc/passwd', turno: 1 },
      { tipo: 'sesion', session_id: SID, turno: -1 },
      { tipo: 'engram', id: '412; drop' },
      { tipo: 'engram', id: 0 },
      { tipo: 'url', href: 'https://x' },
      { tipo: 'engram', id: 412, titulo: 'repetida' },
    ])
    expect(items.map((f) => f.tipo)).toEqual(['sesion', 'engram'])
    expect(items[1]).toMatchObject({ proyecto: 'acme', fecha: '2026-09-18' })
  })

  it('corta en 6 y tolera basura', () => {
    expect(toFuentes(Array.from({ length: 9 }, (_, i) => ({ tipo: 'engram', id: i + 1 }))).items).toHaveLength(6)
    expect(toFuentes(undefined).items).toEqual([])
    expect(toFuentes({ tipo: 'engram', id: 1 }).items).toEqual([])
  })

  it('pone títulos por defecto y recorta los largos', () => {
    const [s, e] = toFuentes([{ tipo: 'sesion', session_id: SID, turno: 0 }, { tipo: 'engram', id: 7, titulo: 'x'.repeat(200), fecha: 'ayer' }]).items
    expect(s.titulo).toBe('Sesión')
    expect(e.titulo).toHaveLength(80)
    expect(e.fecha).toBe('')
  })
})

describe('splitFuentes', () => {
  it('saca el bloque del texto', () => {
    const r = splitFuentes(bloque(`[{"tipo": "engram", "id": 412, "titulo": "Docker", "fecha": "2026-09-18"}]`), false)
    expect(r.text).toBe('Lo levantamos con el override.')
    expect(r.fuentes).toHaveLength(1)
  })

  it('esconde un bloque roto en vez de mostrarlo como código', () => {
    const r = splitFuentes(bloque('[{"tipo": "engram", "id": '), false)
    expect(r.text).toBe('Lo levantamos con el override.')
    expect(r.fuentes).toEqual([])
  })

  it('mientras llega, esconde el bloque abierto', () => {
    const r = splitFuentes('Lo levantamos.\n\n```fuentes\n[{"tipo": "eng', true)
    expect(r).toEqual({ text: 'Lo levantamos.', fuentes: [], pending: true })
  })

  it('deja el texto sin bloque tal cual', () => {
    expect(splitFuentes('hola', false)).toEqual({ text: 'hola', fuentes: [], pending: false })
  })

  it('conserva lo que viene después del bloque', () => {
    const r = splitFuentes(bloque('[]') + '\n\nPosdata', false)
    expect(r.text).toBe('Lo levantamos con el override.\n\nPosdata')
  })
})

describe('pasos de memoria', () => {
  it('arma etiquetas legibles', () => {
    expect(pasoMemoria('mcp__memoria__buscar_sesiones', 'docker egress')).toEqual({ icon: 'search', label: 'Buscando en tus sesiones: «docker egress»' })
    expect(pasoMemoria('mcp__memoria__buscar_memoria', 'tienda local').icon).toBe('brain')
    expect(pasoMemoria('mcp__memoria__leer_sesion', 'Entorno local Tienda · 2026-10-01').label).toBe('Leyendo «Entorno local Tienda» (1 oct)')
    expect(pasoMemoria('mcp__memoria__leer_sesion', 'aaaaaaaa').label).toBe('Leyendo una sesión')
    expect(pasoMemoria('mcp__memoria__memoria_reciente', '').label).toBe('Mirando lo último en Engram')
  })

  it('reconoce herramientas de memoria y cuenta lugares', () => {
    expect(esMemoria('mcp__memoria__leer_memoria')).toBe(true)
    expect(esMemoria('Read')).toBe(false)
    expect(lugares(1)).toBe('Buscó en 1 lugar')
    expect(lugares(3)).toBe('Buscó en 3 lugares')
  })

  it('formatea fechas cortas y referencias de cita', () => {
    expect(fechaCorta('2026-09-18')).toBe('18 sep')
    expect(fechaCorta('')).toBe('')
    expect(citaRef({ tipo: 'engram', id: 4, titulo: '', fecha: '', proyecto: '' })).toEqual({ tipo: 'engram', id: 4 })
  })
})

describe('resumenIndice', () => {
  const base = { indexados: 93, tamano_mb: 24.3, ultima_actualizacion: '2026-11-01T10:00:00Z', actualizando: false }
  it('resume sesiones, tamaño y antigüedad', () => {
    expect(resumenIndice(base, 'hace 2 min')).toBe('93 sesiones · 24 MB · actualizado hace 2 min')
    expect(resumenIndice({ ...base, indexados: 1, tamano_mb: 0.4 }, 'recién')).toBe('1 sesión · 0,4 MB · actualizado recién')
    expect(resumenIndice({ ...base, actualizando: true }, 'hace 2 min')).toBe('93 sesiones · 24 MB · actualizando…')
  })
  it('avisa cuando está vacío o armándose', () => {
    expect(resumenIndice({ ...base, indexados: 0 }, '')).toBe('Todavía no hay nada indexado')
    expect(resumenIndice({ ...base, indexados: 0, actualizando: true }, '')).toBe('Armando el índice…')
  })
})
