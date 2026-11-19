import { reactive } from 'vue'
import { getCambios, type Cambios } from '../api/cambiosApi'
import { ApiError } from '../api/types'

export const cambios = reactive<{ sid: string; data: Cambios | null; loading: boolean; error: string }>({
  sid: '', data: null, loading: false, error: '',
})

let seq = 0
let fetcher: (sid: string, refrescar?: boolean) => Promise<Cambios> = getCambios

export function setCambiosApi(f: typeof fetcher): void {
  fetcher = f
}

export async function cargarCambios(sid: string, refrescar = false): Promise<void> {
  const mine = ++seq
  if (cambios.sid !== sid) {
    cambios.sid = sid
    cambios.data = null
  }
  cambios.loading = true
  cambios.error = ''
  try {
    const data = await fetcher(sid, refrescar)
    if (mine === seq) cambios.data = data
  } catch (e) {
    if (mine === seq) cambios.error = e instanceof ApiError && e.detail ? e.detail : 'No pude leer los cambios'
  } finally {
    if (mine === seq) cambios.loading = false
  }
}

export function limpiarCambios(): void {
  seq++
  cambios.sid = ''
  cambios.data = null
  cambios.loading = false
  cambios.error = ''
}
