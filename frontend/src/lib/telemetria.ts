/** Clave anónima de un "No": hash de sesión, mensaje e índice; nunca el comando ni el id de sesión. */
export async function claveNo(sid: string, mid: string, indice: number): Promise<string | null> {
  const subtle = globalThis.crypto?.subtle
  if (!subtle) return null
  const bytes = new TextEncoder().encode(`${sid}:${mid}:${indice}`)
  const digest = new Uint8Array(await subtle.digest('SHA-256', bytes))
  return Array.from(digest.slice(0, 8), (b) => b.toString(16).padStart(2, '0')).join('')
}
