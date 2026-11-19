import { computed, reactive, watch } from 'vue'
import { ApiError } from '../api/types'
import { mensajeError } from '../lib/errores'
import type { Candidata, Pendiente, ResultadoTodas } from '../api/mudanzaApi'
import { listarMudanza, mudar, mudarTodas, retomarMudanza } from '../api/mudanzaApi'
import { boardState } from './app'
import { haptic } from '../motion'

export const mz = reactive({
  disponible: false,
  motivo: '',
  sesiones: [] as Candidata[],
  pendientes: [] as Pendiente[],
  loaded: false,
  open: false,
  modo: 'una' as 'una' | 'todas',
  objetivo: null as Candidata | null,
  ocupado: false,
  error: '',
  resultado: null as ResultadoTodas | null,
  listo: false,
  listoTxt: '',
  bloqueoMsg: '',
})

export const quietas = computed(() => mz.sesiones.filter((s) => s.puede))

export function puedeMudar(paneId: string): boolean {
  return mz.disponible && quietas.value.some((s) => s.pane_id === paneId)
}

let seq = 0
let timer: ReturnType<typeof setTimeout> | undefined
let started = false

export async function refreshMudanza(): Promise<void> {
  const mine = ++seq
  try {
    const r = await listarMudanza()
    if (mine !== seq) return
    mz.disponible = r.disponible
    mz.motivo = r.motivo
    mz.sesiones = r.sesiones
    mz.pendientes = r.pendientes
    mz.loaded = true
    if (!mz.open) mz.error = ''
  } catch (e) {
    if (mine !== seq) return
    if (mz.open) mz.error = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  }
}

function scheduleRefresh() {
  clearTimeout(timer)
  timer = setTimeout(() => {
    timer = undefined
    void refreshMudanza()
  }, 600)
}

export function iniciarMudanza() {
  if (started) return
  started = true
  watch(() => boardState.value, scheduleRefresh, { immediate: true })
}

export function abrirMudanza(paneId: string) {
  const c = mz.sesiones.find((s) => s.pane_id === paneId)
  if (!c || !c.puede) {
    mz.bloqueoMsg = c?.motivo || mz.motivo || 'Ahora no se puede mudar esa sesión'
    return
  }
  mz.modo = 'una'
  mz.objetivo = c
  mz.error = ''
  mz.resultado = null
  mz.open = true
}

export function abrirMudarTodas() {
  if (!mz.disponible || !quietas.value.length) return
  mz.modo = 'todas'
  mz.objetivo = null
  mz.error = ''
  mz.resultado = null
  mz.open = true
}

export function cerrarMudanza() {
  if (mz.ocupado) return
  mz.open = false
  mz.error = ''
  mz.resultado = null
  mz.objetivo = null
}

export async function confirmarMudanza(): Promise<void> {
  if (mz.ocupado || mz.resultado) return
  mz.ocupado = true
  mz.error = ''
  try {
    if (mz.modo === 'una') {
      const c = mz.objetivo
      if (!c) {
        mz.ocupado = false
        return
      }
      await mudar(c.pane_id)
      haptic(10)
      mz.listoTxt = `«${c.nombre}» en tu terminal`
      mz.listo = true
      mz.ocupado = false
      setTimeout(() => {
        mz.listo = false
        cerrarMudanza()
      }, 1100)
    } else {
      const ids = quietas.value.slice(0, 30).map((s) => s.pane_id)
      mz.resultado = await mudarTodas(ids)
    }
  } catch (e) {
    mz.error = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  } finally {
    mz.ocupado = false
    void refreshMudanza()
  }
}

export async function retomar(p: Pendiente): Promise<void> {
  if (mz.ocupado) return
  mz.ocupado = true
  try {
    await retomarMudanza(p.id)
    mz.listoTxt = `«${p.nombre}» en tu terminal`
    mz.listo = true
    setTimeout(() => (mz.listo = false), 1100)
  } catch (e) {
    mz.error = mensajeError(e, 'Se cortó la conexión con el servidor')
  } finally {
    mz.ocupado = false
    void refreshMudanza()
  }
}
