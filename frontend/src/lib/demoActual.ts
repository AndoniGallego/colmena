import { esDemo, redBloqueadaEnDemo } from './modoDemo'

/** Build con `VITE_DEMO=1`: sin backend, con datos de ejemplo. */
export const DEMO = esDemo(import.meta.env.VITE_DEMO)

/** En demo ningún `fetch` sale a la red: lo que no resuelva el mock recibe un 404. */
export function bloquearRedEnDemo(win: { fetch: typeof fetch } = window): void {
  win.fetch = () => Promise.resolve(redBloqueadaEnDemo())
}
