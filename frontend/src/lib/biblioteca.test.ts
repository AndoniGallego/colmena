import { describe, expect, it } from 'vitest'
import type { LibItem } from '../api/types'
import { normalizeLibItem } from '../api/normalize'
import {
  reunionOf, resumenOf, groupIndex,
  cardVariant, dayLabel, emptyFilters, diagramaOf, formatSize, groupByDay, insertNuevos, isFiltering, libQuery,
  matchesFilters, mergePage, pruebasOf, TYPE_GROUPS, KIND_LABEL, needsRenewal, neighbours, parseLibLink, pathLabel, safeClaudeUrl, shortcutFor,
  TOKEN_RENEW_MS, viewerKind, libIdsPorDiagrama, chunkIds, pickIds, quitadoToast, removeIds,
} from './biblioteca'

const ID = 'a'.repeat(32)

const item = (over: Partial<LibItem> = {}): LibItem => ({
  id: ID, kind: 'html', source: 'Artifact', session_id: 's1', session_titulo: 'Sesión', project: 'p', subagent: '',
  ts: '2026-11-01T15:00:00', title: 'Tablero', description: '', caption: '', nombre: 'a.html', donde: '', exists: true,
  copia: true, servible: true, motivo: '', size: 10, mime: '', url: '', version: 1, versions: [], diagrama_raw: '', src: 'x',
  ...over,
})

describe('parseLibLink', () => {
  it('lee un id válido, la sección sola y rechaza lo raro', () => {
    expect(parseLibLink(`?biblioteca=${ID}`)).toEqual({ id: ID })
    expect(parseLibLink('?biblioteca=')).toEqual({ id: null })
    expect(parseLibLink('?biblioteca=../etc')).toBeNull()
    expect(parseLibLink('?biblioteca=ABC')).toBeNull()
    expect(parseLibLink('?otra=1')).toBeNull()
  })
})

describe('filtros', () => {
  it('libQuery arma solo lo que hay', () => {
    expect(libQuery(emptyFilters())).toBe('')
    const f = { tipo: ['html', 'svg'] as const, session: 's', desde: '2026-10-01', hasta: '', q: ' hola ' }
    expect(libQuery({ ...f, tipo: [...f.tipo] }, 'c1', 30)).toBe('tipo=html%2Csvg&session=s&desde=2026-10-01&q=hola&cursor=c1&limit=30')
    expect(libQuery({ ...emptyFilters(), q: 'x'.repeat(300) }).length).toBeLessThan(120)
  })

  it('isFiltering ignora espacios', () => {
    expect(isFiltering({ ...emptyFilters(), q: '  ' })).toBe(false)
    expect(isFiltering({ ...emptyFilters(), tipo: ['pdf'] })).toBe(true)
  })

  it('matchesFilters combina tipo, sesión, fechas y texto sin tildes', () => {
    const it1 = item({ title: 'Reservas de stock' })
    expect(matchesFilters(it1, emptyFilters())).toBe(true)
    expect(matchesFilters(it1, { ...emptyFilters(), tipo: ['pdf'] })).toBe(false)
    expect(matchesFilters(it1, { ...emptyFilters(), session: 'otra' })).toBe(false)
    expect(matchesFilters(it1, { ...emptyFilters(), desde: '2026-11-02' })).toBe(false)
    expect(matchesFilters(it1, { ...emptyFilters(), hasta: '2026-10-31' })).toBe(false)
    expect(matchesFilters(it1, { ...emptyFilters(), desde: '2026-11-01', hasta: '2026-11-01' })).toBe(true)
    expect(matchesFilters(it1, { ...emptyFilters(), q: 'RESÉRVAS' })).toBe(true)
    expect(matchesFilters(it1, { ...emptyFilters(), q: 'otra cosa' })).toBe(false)
  })
})

describe('listas', () => {
  const mk = (id: string, ts: string) => item({ id: id.repeat(32), ts })

  it('mergePage no repite ítems', () => {
    const a = mk('a', '2026-11-01T10:00:00')
    const b = mk('b', '2026-11-01T09:00:00')
    expect(mergePage([a], [a, b]).map((i) => i.id[0])).toEqual(['a', 'b'])
  })

  it('insertNuevos reemplaza lo viejo y ordena por fecha', () => {
    const old = mk('a', '2026-11-01T08:00:00')
    const mid = mk('b', '2026-11-01T09:00:00')
    const fresh = { ...mk('a', '2026-11-01T11:00:00'), title: 'nuevo' }
    const out = insertNuevos([mid, old], [fresh])
    expect(out.map((i) => i.id[0])).toEqual(['a', 'b'])
    expect(out[0].title).toBe('nuevo')
  })

  it('neighbours sale de la lista cargada', () => {
    const [a, b, c] = ['a', 'b', 'c'].map((x) => mk(x, '2026-11-01T10:00:00'))
    expect(neighbours([a, b, c], b.id)).toEqual({ prev: a, next: c })
    expect(neighbours([a, b, c], a.id).prev).toBeNull()
    expect(neighbours([a], 'z'.repeat(32))).toEqual({ prev: null, next: null })
  })
})

describe('shortcutFor', () => {
  it('mapea teclas y respeta modificadores', () => {
    expect(shortcutFor({ key: '/' }, false)).toBe('search')
    expect(shortcutFor({ key: 'J' }, false)).toBe('down')
    expect(shortcutFor({ key: ' ' }, false)).toBe('quick')
    expect(shortcutFor({ key: '3' }, false)).toBe('type3')
    expect(shortcutFor({ key: 'c', metaKey: true }, false)).toBeNull()
    expect(shortcutFor({ key: 'x' }, false)).toBeNull()
  })

  it('escribiendo solo Esc hace algo', () => {
    expect(shortcutFor({ key: 'j' }, true)).toBeNull()
    expect(shortcutFor({ key: '/' }, true)).toBeNull()
    expect(shortcutFor({ key: 'Escape' }, true)).toBe('escape')
  })
})

describe('token', () => {
  it('se renueva a los 25 minutos', () => {
    expect(needsRenewal(0, TOKEN_RENEW_MS - 1)).toBe(false)
    expect(needsRenewal(0, TOKEN_RENEW_MS)).toBe(true)
  })
})

describe('cardVariant y viewerKind', () => {
  it('elige la variante por tipo, existencia y si se sirve', () => {
    expect(cardVariant(item())).toBe('cover')
    expect(cardVariant(item({ servible: false }))).toBe('doc')
    expect(cardVariant(item({ exists: false, copia: false }))).toBe('gone')
    expect(cardVariant(item({ exists: false, copia: true }))).toBe('cover')
    expect(cardVariant(item({ kind: 'image' }))).toBe('image')
    expect(cardVariant(item({ kind: 'gif' }))).toBe('image')
    expect(cardVariant(item({ kind: 'video' }))).toBe('video')
    expect(cardVariant(item({ kind: 'pdf' }))).toBe('doc')
    expect(cardVariant(item({ kind: 'diagrama', exists: false }))).toBe('diagrama')
    expect(cardVariant(item({ kind: 'remoto', exists: false }))).toBe('remoto')
  })

  it('viewerKind', () => {
    expect(viewerKind(item({ kind: 'svg' }))).toBe('frame')
    expect(viewerKind(item({ kind: 'text' }))).toBe('text')
    expect(viewerKind(item({ kind: 'pdf' }))).toBe('pdf')
    expect(viewerKind(item({ kind: 'otro' }))).toBe('gone')
    expect(viewerKind(item({ servible: false }))).toBe('gone')
    expect(viewerKind(item({ kind: 'diagrama', servible: false }))).toBe('diagrama')
  })
})

describe('diagramaOf', () => {
  it('devuelve null si no hay bloque o el conversor lo rechaza', () => {
    expect(diagramaOf(item({ kind: 'diagrama' }), () => ({}) as never)).toBeNull()
    expect(diagramaOf(item({ kind: 'diagrama', diagrama_raw: '{"titulo":"x"}' }), () => null)).toBeNull()
    expect(diagramaOf(item({ kind: 'html', diagrama_raw: '{"nodos":[{"id":"a"}]}' }))).toBeNull()
  })

  it('pasa el JSON al conversor, aun con coma final', () => {
    let seen: unknown
    diagramaOf(item({ kind: 'diagrama', diagrama_raw: '{"titulo": "x",}' }), (raw) => ((seen = raw), null))
    expect(seen).toEqual({ titulo: 'x' })
  })
})

describe('días', () => {
  const now = new Date(2026, 10, 1, 18, 0, 0).getTime()
  const at = (d: number, h: number) => new Date(2026, 10, d, h, 0, 0).toISOString()

  it('dayLabel', () => {
    expect(dayLabel('2026-11-01', now)).toBe('Hoy')
    expect(dayLabel('2026-10-31', now)).toBe('Ayer')
    expect(dayLabel('sin-fecha', now)).toBe('Sin fecha')
    expect(dayLabel('2026-10-20', now)).toMatch(/^[A-ZÁÉÍÓÚ]/)
  })

  it('groupByDay junta días consecutivos', () => {
    const groups = groupByDay([item({ id: '1'.repeat(32), ts: at(1, 15) }), item({ id: '2'.repeat(32), ts: at(1, 9) }), item({ id: '3'.repeat(32), ts: new Date(2026, 9, 20, 10).toISOString() }), item({ id: '4'.repeat(32), ts: 'basura' })], now)
    expect(groups.map((g) => [g.label, g.items.length])).toEqual([['Hoy', 2], [groups[1].label, 1], ['Sin fecha', 1]])
  })
})

describe('texto', () => {
  it('safeClaudeUrl deja pasar solo artifacts de claude.ai', () => {
    expect(safeClaudeUrl('https://claude.ai/artifact/AbCdEf123456')).toBe('https://claude.ai/artifact/AbCdEf123456')
    expect(safeClaudeUrl('https://claude.ai.evil.com/artifact/AbCdEf123456')).toBe('')
    expect(safeClaudeUrl('javascript:alert(1)')).toBe('')
    expect(safeClaudeUrl('http://claude.ai/artifact/AbCdEf123456')).toBe('')
  })

  it('formatSize y pathLabel', () => {
    expect(formatSize(500)).toBe('500 B')
    expect(formatSize(2048)).toBe('2 KB')
    expect(formatSize(3 * 1024 * 1024)).toBe('3.0 MB')
    expect(pathLabel(item({ donde: '~/x', nombre: 'a.html' }))).toBe('~/x')
    expect(pathLabel(item({ donde: '/tmp/s', nombre: 'a.html' }))).toBe('/tmp/s/a.html')
    expect(pathLabel(item({ donde: '', nombre: 'a.html' }))).toBe('a.html')
  })
})

describe('libIdsPorDiagrama', () => {
  const it1 = (id: string, title: string, kind = 'diagrama') => ({ id, kind, title }) as Pick<LibItem, 'id' | 'kind' | 'title'>
  it('matches by title, falls back to order, ignores other kinds', () => {
    const items = [it1('img', 'Captura', 'image'), it1('b', 'Bife'), it1('m', 'Mensaje')]
    expect(libIdsPorDiagrama(['Mensaje', 'Bife'], items)).toEqual(['m', 'b'])
    expect(libIdsPorDiagrama(['Otro', 'Bife'], items)).toEqual(['m', 'b'])
    expect(libIdsPorDiagrama(['x', 'y', 'z'], items)).toEqual(['b', 'm', null])
    expect(libIdsPorDiagrama(['x'], [])).toEqual([null])
  })
})

describe('diagramas en la Biblioteca', () => {
  it('reads every tipo of diagrama item and shows it as a diagram card', () => {
    const d = item({ kind: 'diagrama', diagrama_raw: '{"titulo": "A", "nodos": [{"id": "a"}],}' })
    expect(cardVariant(d)).toBe('diagrama')
    expect(viewerKind(d)).toBe('diagrama')
    expect(diagramaOf(d)).toMatchObject({ tipo: 'estructura', titulo: 'A' })
    const p = item({ kind: 'diagrama', diagrama_raw: '{"titulo": "B", "tipo": "proceso", "pasos": [{"texto": "Uno"}]}' })
    expect(diagramaOf(p)).toMatchObject({ tipo: 'proceso', titulo: 'B' })
    expect(diagramaOf(item({ kind: 'diagrama', diagrama_raw: '{"nodos": 3}' }))).toBeNull()
    expect(diagramaOf(item({ kind: 'html' }))).toBeNull()
  })
})

describe('quitar', () => {
  it('Supr es el atajo de quitar, pero no mientras se escribe', () => {
    expect(shortcutFor({ key: 'Delete' }, false)).toBe('quitar')
    expect(shortcutFor({ key: 'Delete' }, true)).toBeNull()
  })

  it('parte los ids en tandas de 500', () => {
    const ids = Array.from({ length: 1201 }, (_, n) => String(n))
    expect(chunkIds(ids).map((c) => c.length)).toEqual([500, 500, 201])
    expect(chunkIds([])).toEqual([])
  })

  it('saca de la lista solo lo quitado', () => {
    const list = [item({ id: 'a' }), item({ id: 'b' }), item({ id: 'c' })]
    expect(removeIds(list, ['b', 'zz']).map((i) => i.id)).toEqual(['a', 'c'])
  })

  it('pickIds alterna y respeta el orden de la lista', () => {
    const order = ['a', 'b', 'c', 'd']
    expect(pickIds([], order, 'c', null, false)).toEqual(['c'])
    expect(pickIds(['c'], order, 'a', 'c', false)).toEqual(['a', 'c'])
    expect(pickIds(['a', 'c'], order, 'c', 'c', false)).toEqual(['a'])
  })

  it('pickIds con Shift marca o desmarca el tramo', () => {
    const order = ['a', 'b', 'c', 'd']
    expect(pickIds(['a'], order, 'c', 'a', true)).toEqual(['a', 'b', 'c'])
    expect(pickIds(['a', 'b', 'c'], order, 'a', 'c', true)).toEqual([])
    expect(pickIds([], order, 'b', null, true)).toEqual(['b'])
  })

  it('el aviso distingue uno de varios', () => {
    expect(quitadoToast(1)).toBe('Quitado de la Biblioteca')
    expect(quitadoToast(3)).toBe('3 quitados de la Biblioteca')
  })
})

describe('pruebas en la Biblioteca', () => {
  const raw = JSON.stringify({ titulo: 'Checkout', casos: [{ nombre: 'Pago', resultado: 'falla' }] })
  const p = item({ kind: 'pruebas', title: 'Checkout', description: '1 falla', pruebas_raw: raw, servible: false })
  it('se muestra como tarjeta propia y con visor propio', () => {
    expect(cardVariant(p)).toBe('pruebas')
    expect(viewerKind(p)).toBe('pruebas')
    expect(cardVariant(item({ kind: 'pruebas', exists: false, copia: false }))).toBe('pruebas')
  })
  it('lee el informe y tolera uno roto', () => {
    expect(pruebasOf(p)).toMatchObject({ titulo: 'Checkout', casos: [{ nombre: 'Pago', resultado: 'falla' }] })
    expect(pruebasOf(item({ kind: 'pruebas', pruebas_raw: '{no es json' }))).toBeNull()
    expect(pruebasOf(item({ kind: 'pruebas' }))).toBeNull()
    expect(pruebasOf(item({ kind: 'html', pruebas_raw: raw }))).toBeNull()
  })
  it('tiene etiqueta, filtro por tipo y buscador por título y conteo', () => {
    expect(KIND_LABEL.pruebas).toBe('Pruebas')
    expect(TYPE_GROUPS.find((g) => g.label === 'Pruebas')?.tipo).toEqual(['pruebas'])
    expect(shortcutFor({ key: '7' }, false)).toBe('type7')
    const f = { ...emptyFilters(), tipo: ['pruebas' as const] }
    expect(matchesFilters(p, f)).toBe(true)
    expect(matchesFilters(p, { ...emptyFilters(), q: 'checkout' })).toBe(true)
    expect(matchesFilters(p, { ...emptyFilters(), q: '1 falla' })).toBe(true)
  })
})

describe('reuniones', () => {
  const raw = JSON.stringify({ titulo: 'Daily', inicio: 1_795_000_000, fin: 1_795_000_600, duracion_s: 600, motivo: 'terminada', resumen: ['a'] })
  const r = item({ kind: 'reunion', title: 'Daily', reunion_raw: raw, servible: false })
  it('es el grupo 8, con tecla, tarjeta y visor propios', () => {
    expect(TYPE_GROUPS[7]).toEqual({ key: '8', label: 'Reuniones', tipo: ['reunion'] })
    expect(groupIndex(['reunion'])).toBe(7)
    expect(shortcutFor({ key: '8' }, false)).toBe('type8')
    expect(KIND_LABEL.reunion).toBe('Reunión')
    for (const x of [r, item({ kind: 'reunion', exists: false, copia: false })]) {
      expect(cardVariant(x)).toBe('reunion')
      expect(viewerKind(x)).toBe('reunion')
    }
  })
  it('reunionOf lee una válida y da null con vacía, rota o de otro tipo', () => {
    expect(reunionOf(r)).toMatchObject({ titulo: 'Daily', duracion_s: 600 })
    expect(reunionOf(item({ kind: 'reunion', reunion_raw: '' }))).toBeNull()
    expect(reunionOf(item({ kind: 'reunion', reunion_raw: null }))).toBeNull()
    expect(reunionOf(item({ kind: 'reunion', reunion_raw: '{roto' }))).toBeNull()
    expect(reunionOf(item({ kind: 'html', reunion_raw: raw }))).toBeNull()
  })
  it('normalize acepta kind reunion y conserva reunion_raw y tiene_charla', () => {
    expect(normalizeLibItem({ id: ID, kind: 'reunion', reunion_raw: raw, tiene_charla: true })).toMatchObject({ kind: 'reunion', reunion_raw: raw, tiene_charla: true })
    const n = normalizeLibItem({ id: ID, kind: 'reunion', reunion_raw: null })
    expect(n?.reunion_raw).toBeNull()
    expect(n?.tiene_charla).toBe(false)
  })
})

describe('resúmenes', () => {
  const raw = JSON.stringify({ semana: '2026-W47', desde: '2026-11-16', hasta: '2026-11-22', resumen: {}, propuestas: { nuevas: [{ id: 'aaaaaaaaaaaa', texto: 'Algo' }] } })
  it('tiene filtro, etiqueta, variante y visor propios', () => {
    expect(TYPE_GROUPS[8]).toEqual({ key: '9', label: 'Resúmenes', tipo: ['resumen'] })
    expect(KIND_LABEL.resumen).toBe('Resumen')
    expect(shortcutFor({ key: '9' }, false)).toBe('type9')
    expect(cardVariant(item({ kind: 'resumen', exists: false, copia: false }))).toBe('resumen')
    expect(viewerKind(item({ kind: 'resumen' }))).toBe('resumen')
  })
  it('resumenOf lee uno válido y da null con vacío, roto o de otro tipo', () => {
    expect(resumenOf(item({ kind: 'resumen', resumen_raw: raw }))?.propuestas.nuevas[0].id).toBe('aaaaaaaaaaaa')
    expect(resumenOf(item({ kind: 'resumen', resumen_raw: '{roto' }))).toBeNull()
    expect(resumenOf(item({ kind: 'resumen', resumen_raw: '' }))).toBeNull()
    expect(resumenOf(item({ kind: 'resumen', resumen_raw: null }))).toBeNull()
    expect(resumenOf(item({ kind: 'html', resumen_raw: raw }))).toBeNull()
  })
  it('normalize acepta kind resumen y conserva resumen_raw', () => {
    expect(normalizeLibItem({ id: ID, kind: 'resumen', resumen_raw: raw })).toMatchObject({ kind: 'resumen', resumen_raw: raw })
  })
})
