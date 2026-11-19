import { reactive, watch } from 'vue'
import { ApiError, type CopiaCierre, type CloseBlocker, type Guardado, type GuardadoAccion, type ClosePreview, type CloseSession, type CloseTipo } from '../api/types'
import { closeBody, soloUnknown } from '../lib/cerrar'
import { newId } from '../lib/reply'
import { haptic } from '../motion'
import { accionGuardado, ALREADY_DONE, executeClose, guardados, postBorrarCopia, previewClose } from './app'

export interface CloseTarget {
  tipo: CloseTipo
  targetId: string
  label: string
  /** tabs the workspace had when the sheet opened; a workspace with several tabs gets a short arming delay */
  tabCount: number
  origen: 'manual' | 'jefe'
  destino: string
  porQue: string
  /** the id Centinela put in the block, so the server's record resolves the card on any device */
  id?: string
}

export type CopiaEstado = CopiaCierre & { estado: 'pendiente' | 'borrando' | 'borrada' | 'error'; error: string }

export interface CloseState {
  target: (CloseTarget & { id: string }) | null
  phase: 'idle' | 'loading' | 'ready' | 'closing' | 'guardando' | 'done' | 'gone' | 'error'
  preview: ClosePreview | null
  notice: string | null
  error: string | null
  sesiones: CloseSession[]
  /** copias del repo de una tarea que el usuario puede borrar al cerrar */
  copias: CopiaEstado[]
  /** the closure waiting for the sessions to save to Engram */
  lote: Guardado | null
  listoTxt: string
}

export const close = reactive<CloseState>({ target: null, phase: 'idle', preview: null, notice: null, error: null, sesiones: [], copias: [], lote: null, listoTxt: '' })

let token = 0

export function openClose(target: CloseTarget) {
  close.target = { ...target, id: target.origen === 'jefe' && target.id ? target.id : newId() }
  close.preview = null
  close.notice = null
  close.error = null
  close.sesiones = []
  close.lote = null
  close.phase = 'loading'
  void loadPreview()
}

export function dismissClose() {
  if (close.phase === 'closing') return
  token++
  close.lote = null
  close.target = null
  close.phase = 'idle'
  close.preview = null
  close.copias = []
}

export async function loadPreview() {
  const t = close.target
  if (!t) return
  const mine = ++token
  try {
    const p = await previewClose(t.tipo, t.targetId)
    if (mine !== token || close.phase === 'closing' || close.phase === 'guardando' || close.phase === 'done') return
    close.preview = p
    close.error = null
    close.phase = 'ready'
  } catch (e) {
    if (mine !== token || close.phase === 'closing') return
    if (e instanceof ApiError && e.status === 401) return dismissClose()
    close.preview = null
    close.phase = e instanceof ApiError && e.status === 404 ? 'gone' : 'error'
    close.error = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  }
}

/** The board moved under the open sheet: ask the server again so the list and the fingerprint stay true. */
export function refreshPreview() {
  if (close.phase === 'ready') void loadPreview()
}

function finish(sesiones: CloseSession[], aviso?: string, copias: CopiaCierre[] = []) {
  const t = close.target
  if (!t) return
  haptic([12, 40, 20])
  close.listoTxt = aviso || (sesiones.length ? '' : t.tipo === 'tab' ? 'Tab cerrado' : 'Workspace cerrado')
  close.sesiones = sesiones
  close.copias = copias.map((c) => ({ ...c, estado: 'pendiente' as const, error: '' }))
  close.phase = 'done'
  if (!sesiones.length && !copias.length) {
    setTimeout(() => dismissClose(), close.listoTxt ? 1100 : 0)
  }
}

export async function confirmClose(sinGuardar = false, forzar = false): Promise<void> {
  const t = close.target
  const p = close.preview
  if (!t || !p || close.phase !== 'ready') return
  if (p.bloqueantes.length && !(forzar && soloUnknown(p.bloqueantes))) return
  close.phase = 'closing'
  close.notice = null
  try {
    const r = await executeClose(closeBody({ id: t.id, tipo: t.tipo, targetId: t.targetId, huella: p.huella, origen: t.origen, destino: t.destino, porQue: t.porQue, sinGuardar: sinGuardar === true, forzar: forzar === true }))
    if (r.guardando) return enterLote(r.guardando)
    finish(r.sesiones, r.aviso, r.copias)
  } catch (e) {
    if (!(e instanceof ApiError)) {
      close.phase = 'ready'
      close.notice = 'Se cortó la conexión con el servidor'
      return
    }
    if (e.status === 401) return dismissClose()
    if (e.status === 409 && ALREADY_DONE.test(e.detail)) return finish([])
    if (e.status === 404) {
      close.phase = 'gone'
      close.error = 'Ya no está abierto'
      return
    }
    close.phase = 'ready'
    close.notice = e.detail
    if (e.status === 409 && e.bloqueantes.length && close.preview) close.preview = { ...close.preview, bloqueantes: e.bloqueantes as CloseBlocker[] }
    // 403: something forbidden showed up since the preview (e.g. Claude in a protected tab); the sheet re-asks and locks.
    if (e.status === 409 || e.status === 403) void loadPreview()
  }
}

function enterLote(g: Guardado) {
  close.lote = g
  close.phase = 'guardando'
  close.notice = null
  applyLote(g)
}

/** The server pushes the lote on every change: close the sheet when the closure went out, go back to the list if it did not. */
function applyLote(g: Guardado) {
  const t = close.target
  if (!t || g.id !== t.id || close.phase !== 'guardando') return
  close.lote = g
  if (!g.terminado) return
  const target = g.targets[0]
  if (!target) {
    // lote descartado sin targets (otro dispositivo lo resolvió por otro camino): no seguir esperando
    close.phase = 'ready'
    close.notice = 'Ese cierre ya se resolvió: revisalo de nuevo'
    void loadPreview()
    return
  }
  if (target.estado === 'cerrado') return finish(target.sesiones, undefined, target.copias)
  if (target.estado === 'cancelado') return dismissClose()
  close.phase = 'ready'
  close.notice = target.error || 'No se pudo cerrar: revisalo de nuevo'
  void loadPreview()
}

watch(
  () => (close.target ? guardados[close.target.id] : undefined),
  (g) => g && applyLote(g),
  { deep: true },
)

/** "Cerrar igual" / "Esperar más" while the sessions finish saving. */
export async function accionLoteSheet(accion: GuardadoAccion): Promise<void> {
  const g = close.lote
  if (!g || close.phase !== 'guardando') return
  try {
    applyLote(await accionGuardado(g.id, accion))
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) return dismissClose()
    close.notice = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  }
}

/** "Borrar también la copia del repo": solo si el servidor la dio por borrable; él vuelve a revisar y nunca fuerza. */
export async function borrarCopia(ruta: string): Promise<void> {
  const c = close.copias.find((x) => x.ruta === ruta)
  if (!c || !c.borrable || c.estado === 'borrando' || c.estado === 'borrada') return
  c.estado = 'borrando'
  c.error = ''
  try {
    await postBorrarCopia(ruta)
    c.estado = 'borrada'
  } catch (e) {
    c.estado = 'error'
    c.error = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  }
}
