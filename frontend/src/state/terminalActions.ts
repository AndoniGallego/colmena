import { reactive, shallowRef } from 'vue'
import { ApiError, type RepetirPrep, type TerminalAuditoria, type TerminalConfig, type TerminalPreview } from '../api/types'
import { terminalError, type AccionKind } from '../lib/terminales'
import { newId } from '../lib/reply'
import { haptic } from '../motion'
import { cerrarTerminal, enviarComando, getTerminalAuditoria, getTerminalConfig, previewTerminal, repetirConfirmar, repetirPreparar, terminalCtrlC } from './app'
import { forgetVentana, rememberCommand, touchVentana, ventana } from './terminalWrite'
import { closeTerminal, openTerminalId } from './terminales'

export const tconfig = shallowRef<TerminalConfig | null>(null)
export const actividad = shallowRef<TerminalAuditoria[]>([])

export interface AccionState {
  kind: AccionKind | null
  paneId: string
  phase: 'idle' | 'loading' | 'ready' | 'running' | 'error'
  preview: TerminalPreview | null
  prep: RepetirPrep | null
  comando: string
  rapido: number | null
  error: string | null
  listo: boolean
  listoTxt: string
}

/** Sube cada vez que un comando sale bien: el compositor borra su texto al verlo cambiar. */
export const enviados = shallowRef(0)

export const act = reactive<AccionState>({ kind: null, paneId: '', phase: 'idle', preview: null, prep: null, comando: '', rapido: null, error: null, listo: false, listoTxt: '' })

let token = 0
let ctrlId = ''

export async function loadTerminalConfig(): Promise<void> {
  try {
    tconfig.value = await getTerminalConfig()
  } catch {
    tconfig.value = null
  }
}

export async function loadActividad(): Promise<void> {
  try {
    actividad.value = await getTerminalAuditoria(20)
  } catch {
    actividad.value = []
  }
}

function reset() {
  act.kind = null
  act.paneId = ''
  act.phase = 'idle'
  act.preview = null
  act.prep = null
  act.comando = ''
  act.rapido = null
  act.error = null
  act.listo = false
  act.listoTxt = ''
}

export async function openAccion(kind: AccionKind, paneId: string, comando = '', rapido: number | null = null): Promise<void> {
  const mine = ++token
  reset()
  act.kind = kind
  act.paneId = paneId
  act.comando = comando
  act.rapido = rapido
  act.phase = 'loading'
  ctrlId = newId()
  try {
    const preview = await previewTerminal(paneId)
    if (mine !== token) return
    act.preview = preview
    if (preview.protegida) throw Object.assign(new Error('protegida'), { local: 'Ese workspace está protegido' })
    if (kind === 'repetir' || kind === 'comando') {
      if (preview.estado !== 'prompt') throw Object.assign(new Error('corriendo'), { local: `Hay un programa corriendo${preview.proceso ? ` (${preview.proceso})` : ''}: frenalo primero` })
      if (kind === 'comando') {
        act.phase = 'ready'
        return
      }
      act.prep = await repetirPreparar({ id: newId(), pane_id: paneId, huella: preview.huella })
      if (mine !== token) return
      if (!act.prep.linea) throw Object.assign(new Error('vacio'), { local: 'No hay un comando anterior para repetir' })
    }
    act.phase = 'ready'
    // Una terminal en el prompt se cierra sin preguntar; con algo corriendo, o si se lleva su pestaña o el
    // workspace entero, la hoja lo dice y espera.
    if (kind === 'cerrar' && preview.estado === 'prompt' && preview.cierra === 'terminal') await confirmAccion()
  } catch (e) {
    if (mine !== token) return
    act.error = (e as { local?: string }).local ?? terminalError(e)
    act.phase = 'error'
  }
}

export async function confirmAccion(): Promise<void> {
  const { kind, preview, prep } = act
  if (!kind || !preview || act.phase !== 'ready') return
  const mine = token
  act.phase = 'running'
  try {
    if (kind === 'ctrl-c') await terminalCtrlC({ id: ctrlId, pane_id: act.paneId, huella: preview.huella })
    else if (kind === 'comando') {
      const base = { id: ctrlId, pane_id: act.paneId, huella: preview.huella }
      // Con un rápido va también el texto que se confirmó: si la lista cambió, el servidor lo rechaza.
      await enviarComando(act.rapido !== null ? { ...base, rapido: act.rapido, comando: act.comando } : { ...base, comando: act.comando }, ventana.token)
      rememberCommand(act.comando)
      touchVentana()
      enviados.value++
    } else if (kind === 'cerrar') {
      await cerrarTerminal({ id: ctrlId, pane_id: act.paneId, huella: preview.huella })
      if (openTerminalId.value === act.paneId) closeTerminal()
    } else await repetirConfirmar({ id: newId(), pane_id: act.paneId, huella2: prep!.huella2, ejecutar: true })
    if (mine !== token) return
    haptic(12)
    act.listoTxt = ({ 'ctrl-c': 'Ctrl+C enviado', comando: 'Comando enviado', cerrar: 'Terminal cerrada', repetir: 'Comando ejecutado' } as const)[kind]
    act.listo = true
    setTimeout(() => {
      act.listo = false
      reset()
    }, 1100)
    void loadActividad()
  } catch (e) {
    if (mine !== token) return
    if (e instanceof ApiError && e.status === 401) forgetVentana()
    act.error = terminalError(e)
    act.phase = 'error'
    void loadActividad()
  }
}

/** Cerrar sin ejecutar: si ya se subió la línea anterior al prompt, se limpia. */
export function dismissAccion(): void {
  if (act.phase === 'running') return
  const { kind, prep, preview, phase } = act
  token++
  if (kind === 'repetir' && phase === 'ready' && prep?.huella2 && preview) {
    void repetirConfirmar({ id: newId(), pane_id: act.paneId, huella2: prep.huella2, ejecutar: false }).catch(() => {})
  }
  reset()
}
