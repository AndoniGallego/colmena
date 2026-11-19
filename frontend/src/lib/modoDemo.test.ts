import { describe, expect, it } from 'vitest'
import { baseDeBuild, BASE_DEMO, esDemo, rebasarManifest, redBloqueadaEnDemo, registrarServiceWorker, usarMock } from './modoDemo'

describe('esDemo', () => {
  it('solo VITE_DEMO=1 (o true) prende el modo demo', () => {
    expect(esDemo('1')).toBe(true)
    expect(esDemo('true')).toBe(true)
    expect(esDemo('0')).toBe(false)
    expect(esDemo('')).toBe(false)
    expect(esDemo(undefined)).toBe(false)
  })
})

describe('usarMock', () => {
  it('en demo siempre, sin mirar la URL ni el modo dev', () => {
    expect(usarMock({ demo: true, dev: false, search: '' })).toBe(true)
  })
  it('en dev con ?mock queda igual que antes', () => {
    expect(usarMock({ demo: false, dev: true, search: '?mock' })).toBe(true)
    expect(usarMock({ demo: false, dev: true, search: '?x=1&mock=login' })).toBe(true)
    expect(usarMock({ demo: false, dev: true, search: '' })).toBe(false)
  })
  it('en producción normal nunca, aunque la URL traiga ?mock', () => {
    expect(usarMock({ demo: false, dev: false, search: '?mock' })).toBe(false)
  })
})

describe('registrarServiceWorker', () => {
  const ok = { demo: false, prod: true, notch: false, tieneSW: true, seguro: true }
  it('en producción normal se registra', () => {
    expect(registrarServiceWorker(ok)).toBe(true)
  })
  it('en demo no se registra', () => {
    expect(registrarServiceWorker({ ...ok, demo: true })).toBe(false)
  })
  it('sin producción, en el notch, sin soporte o sin contexto seguro, no', () => {
    expect(registrarServiceWorker({ ...ok, prod: false })).toBe(false)
    expect(registrarServiceWorker({ ...ok, notch: true })).toBe(false)
    expect(registrarServiceWorker({ ...ok, tieneSW: false })).toBe(false)
    expect(registrarServiceWorker({ ...ok, seguro: false })).toBe(false)
  })
})

describe('baseDeBuild', () => {
  it('sin demo es / aunque no haya variables', () => {
    expect(baseDeBuild({})).toBe('/')
  })
  it('en demo es /colmena/ por defecto', () => {
    expect(BASE_DEMO).toBe('/colmena/')
    expect(baseDeBuild({ VITE_DEMO: '1' })).toBe('/colmena/')
  })
  it('VITE_BASE manda y se normaliza con barras a los dos lados', () => {
    expect(baseDeBuild({ VITE_DEMO: '1', VITE_BASE: '/otra' })).toBe('/otra/')
    expect(baseDeBuild({ VITE_BASE: 'sub/dir/' })).toBe('/sub/dir/')
    expect(baseDeBuild({ VITE_BASE: '/' })).toBe('/')
  })
})

describe('rebasarManifest', () => {
  const m = {
    start_url: '/',
    scope: '/',
    id: '/',
    icons: [{ src: '/icons/icon-192.png?v=colmena', sizes: '192x192' }],
    shortcuts: [{ name: 'X', url: '/?x=1', icons: [{ src: '/icons/a.png' }] }],
    name: 'Colmena',
  }
  it('con base / no cambia nada', () => {
    expect(rebasarManifest(m, '/')).toEqual(m)
  })
  it('con otra base antepone la base a las rutas absolutas', () => {
    const r = rebasarManifest(m, '/colmena/')
    expect(r.start_url).toBe('/colmena/')
    expect(r.scope).toBe('/colmena/')
    expect(r.id).toBe('/colmena/')
    expect(r.icons[0].src).toBe('/colmena/icons/icon-192.png?v=colmena')
    expect(r.shortcuts[0].url).toBe('/colmena/?x=1')
    expect(r.shortcuts[0].icons[0].src).toBe('/colmena/icons/a.png')
    expect(r.name).toBe('Colmena')
  })
  it('no toca urls ya completas ni rutas ya rebasadas', () => {
    const r = rebasarManifest({ start_url: 'https://x.test/a', icons: [{ src: '/colmena/i.png' }] }, '/colmena/')
    expect(r.start_url).toBe('https://x.test/a')
    expect(r.icons[0].src).toBe('/colmena/i.png')
  })
})

describe('redBloqueadaEnDemo', () => {
  it('responde 404 JSON sin salir a la red', async () => {
    const r = redBloqueadaEnDemo()
    expect(r.status).toBe(404)
    expect(await r.json()).toEqual({ error: 'No disponible en la demo' })
  })
})
