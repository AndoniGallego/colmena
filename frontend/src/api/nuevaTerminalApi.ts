import type { Api } from './types'
import type { CarpetaItem, NuevaTerminalBody } from '../lib/nuevaTerminal'

export type NuevaTerminalResult = { ok: true; espacio_id: string; sesion_id: string }

export type NuevaTerminalApi = {
  listarCarpetas: () => Promise<CarpetaItem[]>
  abrir: (body: NuevaTerminalBody) => Promise<NuevaTerminalResult>
}

export function nuevaTerminalApi(api: Api): NuevaTerminalApi {
  return {
    async listarCarpetas() {
      const d = await api.getTerminalesCarpetas()
      return d.carpetas
    },
    async abrir(body) {
      return api.postTerminalesNueva(body)
    },
  }
}
