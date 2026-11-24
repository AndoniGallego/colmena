const CLAVE = 'orq-device-notch'
const VALIDO = /^[A-Za-z0-9_-]{8,64}$/

function aleatorio(): string {
  const c = globalThis.crypto
  if (c?.randomUUID) return c.randomUUID()
  return Array.from({ length: 4 }, () => Math.random().toString(36).slice(2, 10)).join('')
}

/**
 * Id del dispositivo para el SSE. En el notch (`estable`) se guarda en sessionStorage: una recarga del
 * webview vuelve con el mismo id y la reunión en curso lo sigue reconociendo.
 */
export function deviceId(estable: boolean, store?: Pick<Storage, 'getItem' | 'setItem'>): string {
  if (!estable) return aleatorio()
  try {
    const s = store ?? sessionStorage
    const guardado = s.getItem(CLAVE)
    if (guardado && VALIDO.test(guardado)) return guardado
    const nuevo = aleatorio()
    s.setItem(CLAVE, nuevo)
    return nuevo
  } catch {
    return aleatorio()
  }
}
