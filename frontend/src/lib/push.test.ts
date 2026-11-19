import { describe, expect, it } from 'vitest'
import { DEFAULT_PREFS, deviceName, normalizePrefs, resolveSupport, subscribeRequest, urlBase64ToBytes, type PushEnv } from './push'

const env = (over: Partial<PushEnv> = {}): PushEnv => ({
  ios: false, standalone: false, secure: true, hasWorker: true, hasPush: true, hasNotification: true, permission: 'default', ...over,
})

describe('resolveSupport', () => {
  it('navegador de escritorio con todo disponible', () => expect(resolveSupport(env())).toBe('available'))
  it('iOS sin instalar pide agregar a inicio, aunque no tenga PushManager', () => {
    expect(resolveSupport(env({ ios: true, hasPush: false }))).toBe('install')
  })
  it('iOS instalada puede activar', () => expect(resolveSupport(env({ ios: true, standalone: true }))).toBe('available'))
  it('sin HTTPS o sin APIs no está soportado', () => {
    expect(resolveSupport(env({ secure: false }))).toBe('unsupported')
    expect(resolveSupport(env({ hasPush: false }))).toBe('unsupported')
    expect(resolveSupport(env({ hasNotification: false }))).toBe('unsupported')
  })
  it('permiso denegado', () => expect(resolveSupport(env({ permission: 'denied' }))).toBe('denied'))
})

describe('deviceName', () => {
  it.each([
    ['Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148', 'iPhone'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36 Edg/130.0', 'Windows · Edge'],
    ['Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/130.0 Safari/537.36', 'Windows · Chrome'],
    ['Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36', 'Android · Chrome'],
    ['Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/18 Safari/605.1.15', 'Mac · Safari'],
    ['', 'Navegador'],
  ])('%s', (ua, name) => expect(deviceName(ua)).toBe(name))
})

describe('normalizePrefs', () => {
  it('las prefs de piezas arrancan prendidas y respetan lo guardado', () => {
    expect(normalizePrefs(null, ['demo']).demo).toBe(true)
    expect(normalizePrefs({ demo: false }, ['demo']).demo).toBe(false)
    expect(normalizePrefs({ demo: false })).not.toHaveProperty('demo')
  })
  it('los avances de Centinela arrancan prendidos', () => expect(normalizePrefs(null).progreso).toBe(true))
  it('respeta progreso si viene en el objeto', () => {
    expect(normalizePrefs({ progreso: false })).toEqual({ ...DEFAULT_PREFS, progreso: false })
  })
  it('el interruptor de entornos arranca prendido', () => expect(normalizePrefs(null).entornos).toBe(true))
  it('completa con los valores por defecto', () => expect(normalizePrefs(null)).toEqual(DEFAULT_PREFS))
  it('respeta solo booleanos conocidos', () => {
    expect(normalizePrefs({ asks: false, done: 'no', otro: false })).toEqual({ ...DEFAULT_PREFS, asks: false })
  })
})

describe('urlBase64ToBytes', () => {
  it('decodifica base64url sin padding', () => {
    expect([...urlBase64ToBytes('-_8')]).toEqual([251, 255])
    expect(urlBase64ToBytes('').length).toBe(0)
  })
})

describe('subscribeRequest', () => {
  const prefs = { ...DEFAULT_PREFS }
  it('arma el cuerpo con endpoint, claves, dispositivo y prefs', () => {
    expect(subscribeRequest({ endpoint: 'https://x', keys: { p256dh: 'a', auth: 'b' }, expirationTime: null }, 'iPhone', prefs)).toEqual({
      subscription: { endpoint: 'https://x', keys: { p256dh: 'a', auth: 'b' } }, device: 'iPhone', prefs,
    })
  })
  it('descarta suscripciones sin claves', () => {
    expect(subscribeRequest({ endpoint: 'https://x' }, 'iPhone', prefs)).toBeNull()
    expect(subscribeRequest({ keys: { p256dh: 'a', auth: 'b' } }, 'iPhone', prefs)).toBeNull()
  })
})
