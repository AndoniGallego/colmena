export const URL_REPO = 'https://github.com/AndoniGallego/colmena'
export const BASE_DEMO = '/colmena/'

export const esDemo = (v?: string): boolean => v === '1' || v === 'true'

/** Demo: siempre. Dev: solo con ?mock. Producción normal: nunca. */
export function usarMock(o: { demo: boolean; dev: boolean; search: string }): boolean {
  return o.demo || (o.dev && new URLSearchParams(o.search).has('mock'))
}

export function registrarServiceWorker(o: { demo: boolean; prod: boolean; notch: boolean; tieneSW: boolean; seguro: boolean }): boolean {
  return !o.demo && o.prod && !o.notch && o.tieneSW && o.seguro
}

/** `/` salvo en demo (`/colmena/`); `VITE_BASE` manda y siempre queda con barra a cada lado. */
export function baseDeBuild(env: { VITE_DEMO?: string; VITE_BASE?: string }): string {
  const crudo = env.VITE_BASE?.trim() || (esDemo(env.VITE_DEMO) ? BASE_DEMO : '/')
  const limpio = crudo.replace(/^\/+|\/+$/g, '')
  return limpio ? `/${limpio}/` : '/'
}

const absoluta = (s: string, base: string) => s.startsWith('/') && !s.startsWith('//') && !s.startsWith(base)

/** Antepone `base` a las rutas absolutas del manifest (start_url, scope, id, íconos, shortcuts). */
export function rebasarManifest<T>(manifest: T, base: string): T {
  if (base === '/') return manifest
  const rec = (v: unknown, clave?: string): unknown => {
    if (Array.isArray(v)) return v.map((x) => rec(x, clave))
    if (v && typeof v === 'object') return Object.fromEntries(Object.entries(v).map(([k, x]) => [k, rec(x, k)]))
    if (typeof v === 'string' && ['start_url', 'scope', 'id', 'src', 'url'].includes(clave ?? '') && absoluta(v, base)) {
      return base + v.slice(1)
    }
    return v
  }
  return rec(manifest) as T
}

/** Respuesta de lo que escape al mock en demo: nunca sale a la red. */
export const redBloqueadaEnDemo = (): Response =>
  new Response(JSON.stringify({ error: 'No disponible en la demo' }), { status: 404, headers: { 'content-type': 'application/json' } })
