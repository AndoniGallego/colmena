import type { Api } from './types'
import type { RetomarSesionBody, SesionVieja } from '../lib/retomarSesion'
export type RetomarSesionResult = { ok: true; espacio_id: string; sesion_id: string; pane_id?: string }

export function getSesionesViejas(api: Api, q = ''): Promise<SesionVieja[]> {
  const qs = q ? `?q=${encodeURIComponent(q)}` : ''
  return api.getSesionesViejas(qs)
}

export function postRetomarSesion(api: Api, body: RetomarSesionBody): Promise<RetomarSesionResult> {
  return api.postSesionesViejasRetomar(body)
}
