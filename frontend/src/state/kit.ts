import { reactive, ref } from 'vue'
import { arreglarKit, getKit, getRegla, type Kit, type ReglaKit, type ResultadoArreglo } from '../api/kitApi'
import { mensajeError } from '../lib/errores'
import { ApiError } from '../api/types'

export interface ApiKit {
  getKit: () => Promise<Kit>
  getRegla: (id: string) => Promise<string>
  arreglarKit: () => Promise<ResultadoArreglo>
}

let api: ApiKit = { getKit: () => getKit(), getRegla: (id) => getRegla(id), arreglarKit: () => arreglarKit() }

export function setKitApi(a: ApiKit): void {
  api = a
}

export const kitOpen = ref(false)
let pushed = false

export const kit = reactive({
  data: null as Kit | null,
  cargando: false,
  error: '',
  arreglando: false,
  errorArreglo: '',
  regla: null as { id: string; titulo: string; texto: string; cargando: boolean; error: string } | null,
})

export async function cargarKit(): Promise<void> {
  kit.cargando = true
  kit.error = ''
  try {
    kit.data = await api.getKit()
  } catch (e) {
    kit.error = mensajeError(e, 'No pude leer el estado del kit.')
  } finally {
    kit.cargando = false
  }
}

export async function arreglar(): Promise<void> {
  if (kit.arreglando) return
  kit.arreglando = true
  kit.errorArreglo = ''
  try {
    const r = await api.arreglarKit()
    if (kit.data) kit.data.estado = r.estado
    if (!r.ok) kit.errorArreglo = r.error || 'No pude arreglar el kit.'
  } catch (e) {
    kit.errorArreglo =
      e instanceof ApiError && e.status === 409
        ? 'Ya se está arreglando el kit: esperá a que termine y revisá de nuevo.'
        : mensajeError(e, 'No pude arreglar el kit.')
  } finally {
    kit.arreglando = false
  }
}

let seqRegla = 0

export async function abrirRegla(r: ReglaKit): Promise<void> {
  const mia = ++seqRegla
  kit.regla = { id: r.id, titulo: r.titulo, texto: '', cargando: true, error: '' }
  try {
    const texto = await api.getRegla(r.id)
    if (mia === seqRegla && kit.regla) kit.regla.texto = texto
  } catch (e) {
    if (mia === seqRegla && kit.regla) kit.regla.error = mensajeError(e, 'No pude leer la regla.')
  } finally {
    if (mia === seqRegla && kit.regla) kit.regla.cargando = false
  }
}

export function cerrarRegla(): void {
  seqRegla++
  kit.regla = null
}

export function openKit(): void {
  if (kitOpen.value) return
  history.pushState({ ...(history.state ?? {}), orqKit: true }, '')
  pushed = true
  kitOpen.value = true
}

export function closeKit(): void {
  if (!kitOpen.value) return
  if (pushed && history.state?.orqKit) history.back()
  else {
    pushed = false
    kitOpen.value = false
  }
}

/** Al perder la sesión: cierra sin tocar el historial. */
export function resetKit(): void {
  kitOpen.value = false
  pushed = false
  cerrarRegla()
  kit.data = null
  kit.error = ''
  kit.errorArreglo = ''
}

if (typeof window !== 'undefined') {
  window.addEventListener('popstate', () => {
    if (kitOpen.value && !history.state?.orqKit) {
      kitOpen.value = false
      pushed = false
    }
  })
}
