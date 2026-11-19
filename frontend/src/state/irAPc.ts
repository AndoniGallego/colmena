import { ref } from 'vue'
import { ApiError } from '../api/types'
import { irAPc } from './app'

const AVISO_MS = 3000

export const irAPcEnviando = ref<Record<string, boolean>>({})
export const irAPcAviso = ref<{ sid: string; texto: string; ok: boolean } | null>(null)

let timer: ReturnType<typeof setTimeout> | undefined

function avisar(sid: string, texto: string, ok: boolean) {
  irAPcAviso.value = { sid, texto, ok }
  clearTimeout(timer)
  timer = setTimeout(() => (irAPcAviso.value = null), AVISO_MS)
}

export async function irAPcSesion(sid: string): Promise<void> {
  if (irAPcEnviando.value[sid]) return
  irAPcEnviando.value = { ...irAPcEnviando.value, [sid]: true }
  if (irAPcAviso.value?.sid === sid) irAPcAviso.value = null
  try {
    await irAPc(sid)
    avisar(sid, 'Abierta en la notebook', true)
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return
    avisar(sid, e instanceof ApiError && e.detail ? e.detail : 'No pude abrir la notebook', false)
  } finally {
    const { [sid]: _fin, ...resto } = irAPcEnviando.value
    irAPcEnviando.value = resto
  }
}
