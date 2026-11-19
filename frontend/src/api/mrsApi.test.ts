import { afterEach, describe, expect, it, vi } from 'vitest'
import { httpMrsApi, normalizeDestinos, normalizeDetalle, normalizeListado, normalizeMr, refPath } from './mrsApi'

const base = { ref: '101:412', project_id: 101, iid: 412, repo: 'g/r', repo_corto: 'r', titulo: 'feat: x', rama: 'feature/X-1', target: 'develop', rol: 'autor', pipeline: { estado: 'fallo', id: 9, url: 'https://gitlab.com/g/r/-/pipelines/9' }, sha: 'a'.repeat(40), creado: '2026-10-01T09:00:00Z', pausado: true }

describe('refPath', () => {
  it('arma la ruta solo con dos enteros', () => {
    expect(refPath('101:412')).toBe('101/412')
  })
  it.each(['101:4;12', '../1:2', '1:2/../../x', 'a:1', '1:2 ', ''])('rechaza %s', (ref) => {
    expect(() => refPath(ref)).toThrow()
  })
})

describe('normalizeMr', () => {
  it('descarta refs inválidos', () => {
    expect(normalizeMr({ ...base, ref: 'x' })).toBeNull()
  })
  it('limpia estado, urls ajenas y sha', () => {
    const m = normalizeMr({ ...base, pipeline: { estado: 'raro', url: 'javascript:alert(1)' }, url: 'https://evil.com/x', sha: 'zz', rol: 'otro' })!
    expect(m.pipeline).toEqual({ estado: 'sin', id: 0, url: '' })
    expect(m.url).toBe('')
    expect(m.sha).toBe('')
    expect(m.rol).toBe('autor')
    expect(m.aprobaciones).toEqual({ dadas: 0, requeridas: 0, faltan: 0, por: [], yo: false, puedo: false })
  })
  it('conserva lo válido', () => {
    const m = normalizeMr(base)!
    expect(m.pipeline.estado).toBe('fallo')
    expect(m.pipeline.url).toBe(base.pipeline.url)
    expect(m.sha).toBe(base.sha)
    expect(m.creado).toBe('2026-10-01T09:00:00Z')
    expect(m.pausado).toBe(true)
  })
})

describe('normalizeListado y detalle', () => {
  it('filtra sesiones con refs inválidos', () => {
    const l = normalizeListado({ items: [base, { ref: 'nope' }], sesiones: { s1: '101:412', s2: '1:2;rm' } })
    expect(l.items).toHaveLength(1)
    expect(l.sesiones).toEqual({ s1: '101:412' })
    expect(l.disponible).toBe(true)
    expect(l.habilitado).toBe(true)
  })
  it('marca deshabilitado cuando el backend lo apaga', () => {
    expect(normalizeListado({ habilitado: false, items: [], sesiones: {} }).habilitado).toBe(false)
  })
  it('descarta jobs sin id y normaliza archivos', () => {
    const d = normalizeDetalle({ ...base, jobs: [{ id: 0 }, { id: 5, estado: 'ok', nombre: 'test' }], archivos: [{ path: 'a.py', nuevo: 'si' }], hilos: [{ id: 'h', notas: [{ id: 1, cuerpo: 'hola' }] }] })!
    expect(d.jobs.map((j) => j.id)).toEqual([5])
    expect(d.archivos[0].nuevo).toBe(false)
    expect(d.hilos[0].notas[0].cuerpo).toBe('hola')
    expect(d.actividad).toEqual([])
    const conAct = normalizeDetalle({ ...base, actividad: [{ id: 0 }, { id: 3, cuerpo: 'added 1 commit', autor: { username: 'u' } }, 'x'] })!
    expect(conAct.actividad.map((e) => [e.id, e.cuerpo, e.autor.username])).toEqual([[3, 'added 1 commit', 'u']])
  })
})

describe('httpMrsApi', () => {
  afterEach(() => vi.unstubAllGlobals())

  it('manda el PIN y el sha al mergear, y propaga Retry-After', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ detail: 'Demasiados intentos' }), { status: 429, headers: { 'Retry-After': '60' } }))
    vi.stubGlobal('fetch', fetch)
    await expect(httpMrsApi.mergear('1:2', '1234', 'a'.repeat(40))).rejects.toMatchObject({ status: 429, retryAfter: 60, message: 'Demasiados intentos' })
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/mrs/1/2/mergear')
    expect(JSON.parse(init.body as string)).toEqual({ pin: '1234', sha: 'a'.repeat(40) })
  })

  it('no llama al servidor con un ref inválido', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await expect(httpMrsApi.cerrar('1:2/../x', '1')).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('POST pausar', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ pausado: true }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    await httpMrsApi.pausar('7:1', true)
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit]
    expect(url).toBe('/api/mrs/7/1/pausa')
    expect(JSON.parse(init.body as string)).toEqual({ pausar: true })
  })
})


describe('pedirActualizar', () => {
  afterEach(() => vi.unstubAllGlobals())
  it('hace POST sin contenido a la ruta del MR', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ok: true }) })
    vi.stubGlobal('fetch', fetchMock)
    await httpMrsApi.pedirActualizar('101:412')
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/mrs/101/412/pedir-actualizar')
    expect(init.method).toBe('POST')
    expect(init.body).toBe('{}')
  })
})

describe('destinos para mandar a una sesión', () => {
  it('normaliza y descarta lo que no es una sesión', () => {
    const d = normalizeDestinos({
      sugerida: 'sess-a',
      sesiones: [
        { session_id: 'sess-a', pane_id: 'w1:p1', nombre: 'Mi sesión', status: 'idle', carpeta_corta: 'x/y', asociada: true },
        { session_id: 'mal id!', pane_id: 'w1:p2' },
        { pane_id: 'w1:p3' },
        { session_id: 'sess-b', pane_id: 'w1:p4', asociada: 'si' },
      ],
    })
    expect(d.sugerida).toBe('sess-a')
    expect(d.sesiones.map((x) => [x.session_id, x.asociada])).toEqual([['sess-a', true], ['sess-b', false]])
    expect(normalizeDestinos(null)).toEqual({ sugerida: null, sesiones: [] })
    expect(normalizeDestinos({ sugerida: 'raro id!', sesiones: [] }).sugerida).toBeNull()
  })

  it('llama a las rutas con solo ids', async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true, sugerida: null, sesiones: [] }), { status: 200 }))
    vi.stubGlobal('fetch', fetch)
    await httpMrsApi.destinos('7:1')
    await httpMrsApi.jobASesion('7:1', 900, 'sess-a')
    await httpMrsApi.hiloASesion('7:1', 'ab12cd34', 'sess-a')
    const urls = (fetch.mock.calls as unknown as [string, RequestInit][]).map(([u, i]) => [u, i.method, i.body])
    expect(urls).toEqual([
      ['/api/mrs/7/1/destinos', 'GET', undefined],
      ['/api/mrs/7/1/jobs/900/a-sesion', 'POST', JSON.stringify({ session_id: 'sess-a' })],
      ['/api/mrs/7/1/hilos/ab12cd34/a-sesion', 'POST', JSON.stringify({ session_id: 'sess-a' })],
    ])
  })

  it('rechaza ids raros sin llamar', async () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await expect(httpMrsApi.hiloASesion('7:1', '../x', 'sess-a')).rejects.toThrow()
    await expect(httpMrsApi.jobASesion('7:1', -1, 'sess-a')).rejects.toThrow()
    expect(fetch).not.toHaveBeenCalled()
  })
})
