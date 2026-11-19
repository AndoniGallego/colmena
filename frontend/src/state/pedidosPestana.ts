import { reactive, watch } from 'vue'
import { ApiError, type PedidoPestana, type PedidoPestanaEstado, type VistaCierrePedido } from '../api/types'
import {
  limpiarPedidoEnUrl,
  mensajeErrorAbrirPedidoPestana,
  pedidoIdDesdeBusqueda,
} from '../lib/pedidosPestana'
import {
  abrirPedidoPestana as apiAbrir,
  auth,
  avisoEvent,
  boardState,
  getPedidosPestana,
  pedidoPestanaEvent,
  rechazarPedidoPestana as apiRechazar,
  vistaCierrePedido,
} from './app'
import { closeTerminal, openTerminal, openTerminalId } from './terminales'
import { terminalError } from '../lib/terminales'

export interface AccionPedidoPestana {
  enviando?: boolean
  error?: string
  pane_id?: string
  vista?: VistaCierrePedido
}

export const pedidosPestana = reactive({
  items: [] as PedidoPestana[],
  porId: {} as Record<string, AccionPedidoPestana>,
  foco: null as string | null,
  listo: false,
  listoTxt: '',
})

let started = false
let cargando = false
// Pedidos que el servidor cerró mientras su apertura seguía en curso: se quitan al terminar la respuesta.
const cerradosEnEnvio = new Set<string>()
const DEBOUNCE_TABLERO_MS = 1000
// Última carga de vista pedida por id: una respuesta vieja que llega tarde se descarta.
const secVista = new Map<string, number>()
let timerTablero: ReturnType<typeof setTimeout> | null = null

function cancelarTimerTablero(): void {
  if (timerTablero !== null) clearTimeout(timerTablero)
  timerTablero = null
}

export function _resetPedidosPestana(): void {
  started = false
  cargando = false
  cerradosEnEnvio.clear()
  secVista.clear()
  cancelarTimerTablero()
  pedidosPestana.items = []
  pedidosPestana.porId = {}
  pedidosPestana.foco = null
  pedidosPestana.listo = false
  pedidosPestana.listoTxt = ''
}

function quitar(id: string): void {
  pedidosPestana.items = pedidosPestana.items.filter((p) => p.id !== id)
}

export function pedidosDeSesion(sid: string | null | undefined): PedidoPestana[] {
  if (!sid) return []
  const ahora = Date.now()
  return pedidosPestana.items
    .filter((p) => p.origen.session_id === sid && p.vence * 1000 > ahora)
    .sort((a, b) => a.ts - b.ts)
}

export async function cargarVistaCierre(id: string): Promise<void> {
  const seq = (secVista.get(id) ?? 0) + 1
  secVista.set(id, seq)
  try {
    const vista = await vistaCierrePedido(id)
    if (secVista.get(id) !== seq || !pedidoPestanaPorId(id)) return
    const cur = pedidosPestana.porId[id] ?? {}
    pedidosPestana.porId = { ...pedidosPestana.porId, [id]: { ...cur, vista } }
  } catch (e) {
    // Un 409 deja el pedido pendiente en el servidor (y los rechazos reales llegan por SSE); un 404 durante un
    // envío es la propia aprobación que lo tomó.
    const status = e instanceof ApiError ? e.status : 0
    if (status === 404 && !pedidosPestana.porId[id]?.enviando) quitar(id)
  }
}

export function pedidoPestanaPorId(id: string): PedidoPestana | undefined {
  return pedidosPestana.items.find((p) => p.id === id)
}

export function pedidoPestanaPendiente(id: string | undefined): boolean {
  if (!id) return false
  const p = pedidoPestanaPorId(id)
  if (!p) return false
  return p.vence * 1000 > Date.now()
}

export function aplicarPedidoPestanaSse(id: string, estado: PedidoPestanaEstado): void {
  if (estado === 'pendiente') {
    void refrescarPedidosPestana()
    return
  }
  if (pedidosPestana.porId[id]?.enviando) {
    cerradosEnEnvio.add(id)
    return
  }
  quitar(id)
}

export async function refrescarPedidosPestana(): Promise<void> {
  if (auth.value !== 'ready' || cargando) return
  cargando = true
  try {
    const nuevos = await getPedidosPestana()
    const enEnvio = pedidosPestana.items.filter(
      (p) => pedidosPestana.porId[p.id]?.enviando && !nuevos.some((n) => n.id === p.id),
    )
    for (const p of enEnvio) cerradosEnEnvio.add(p.id)
    pedidosPestana.items = [...enEnvio, ...nuevos]
  } catch {
    /* el próximo evento reintenta */
  } finally {
    cargando = false
  }
  const sinVista = pedidosPestana.items.filter((p) => p.cierre && !pedidosPestana.porId[p.id]?.vista)
  await Promise.all(sinVista.map((p) => cargarVistaCierre(p.id)))
}

function marcarEnviando(id: string, on: boolean): void {
  const cur = pedidosPestana.porId[id] ?? {}
  pedidosPestana.porId = { ...pedidosPestana.porId, [id]: { ...cur, enviando: on, ...(on ? { error: '' } : {}) } }
}

function avisarListo(txt: string) {
  pedidosPestana.listoTxt = txt
  pedidosPestana.listo = true
  setTimeout(() => {
    pedidosPestana.listo = false
  }, 1100)
}

export async function abrirPedidoPestana(id: string): Promise<void> {
  if (pedidosPestana.porId[id]?.enviando) return
  marcarEnviando(id, true)
  try {
    const p = pedidoPestanaPorId(id)
    const n = p?.pestanas?.length ?? 1
    if (p?.cierre) {
      const vista = pedidosPestana.porId[id]?.vista
      if (!vista) {
        // Sin vista no se sabe qué se aprueba: se carga y se decide con lo que se ve.
        await cargarVistaCierre(id)
        return
      }
      const r = await apiAbrir(id, { huella: vista?.huella ?? '', forzar: vista?.trabajando === true })
      quitar(id)
      pedidosPestana.porId = { ...pedidosPestana.porId, [id]: {} }
      avisarListo(r.guardando ? 'Guardando y cerrando' : 'Cerrado')
      return
    }
    const r = await apiAbrir(id)
    quitar(id)
    if (p?.accion === 'cerrar') {
      pedidosPestana.porId = { ...pedidosPestana.porId, [id]: { pane_id: r.pane_id } }
      avisarListo('Terminal cerrada')
      if (openTerminalId.value === r.pane_id) closeTerminal()
      return
    }
    const aviso: AccionPedidoPestana = { pane_id: r.pane_id }
    if (r.pegado === false) aviso.error = 'Se abrió, pero no pude pegar el mensaje'
    pedidosPestana.porId = { ...pedidosPestana.porId, [id]: aviso }
    avisarListo(n > 1 ? `${n} pestañas abiertas` : 'Pestaña abierta')
    const foco = r.pane_ids?.[0] ?? r.pane_id
    try {
      openTerminal(foco)
    } catch {
      /* la pestaña igual quedó abierta en el servidor */
    }
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0
    if (pedidoPestanaPorId(id)?.cierre && e instanceof ApiError && status === 409 && e.bloqueantes.length) {
      await cargarVistaCierre(id)
      return
    }
    if (pedidoPestanaPorId(id)?.cierre) {
      const detail = e instanceof ApiError ? e.detail ?? '' : ''
      const decidido = status === 409 && /ya no está pendiente/.test(detail)
      const texto = decidido ? 'Ya se decidió' : detail || (status === 404 ? 'Ya no está: descarté el pedido' : 'No pude cerrarlo')
      pedidosPestana.porId = { ...pedidosPestana.porId, [id]: { ...pedidosPestana.porId[id], error: texto } }
      if (status === 404 || decidido || /descarté el pedido/.test(detail)) quitar(id)
      return
    }
    if (pedidoPestanaPorId(id)?.accion === 'cerrar') {
      // El servidor dice por qué no cerró (la terminal cambió, es de Claude...): la tarjeta queda para decidir de nuevo,
      // salvo que el pedido o la terminal ya no existan o ya se haya decidido.
      const detail = e instanceof ApiError ? e.detail ?? '' : ''
      const decidido = status === 409 && /ya no está pendiente/.test(detail)
      pedidosPestana.porId = { ...pedidosPestana.porId, [id]: { ...pedidosPestana.porId[id], error: decidido ? 'Ya se decidió' : terminalError(e) } }
      if (status === 404 || decidido || /descarté el pedido/.test(detail)) quitar(id)
      return
    }
    pedidosPestana.porId = {
      ...pedidosPestana.porId,
      [id]: { error: mensajeErrorAbrirPedidoPestana(status) },
    }
    if (status === 404 || status === 409) quitar(id)
  } finally {
    marcarEnviando(id, false)
    if (cerradosEnEnvio.delete(id)) quitar(id)
  }
}

export async function rechazarPedidoPestana(id: string): Promise<void> {
  if (pedidosPestana.porId[id]?.enviando) return
  marcarEnviando(id, true)
  try {
    await apiRechazar(id)
    quitar(id)
  } catch (e) {
    const status = e instanceof ApiError ? e.status : 0
    pedidosPestana.porId = {
      ...pedidosPestana.porId,
      [id]: { error: mensajeErrorAbrirPedidoPestana(status) },
    }
    if (status === 404 || status === 409) quitar(id)
  } finally {
    marcarEnviando(id, false)
    if (cerradosEnEnvio.delete(id)) quitar(id)
  }
}

export function enfocarPedidoPestana(id: string): void {
  pedidosPestana.foco = id
  void import('./avisos').then((m) => m.abrirAvisos())
}

function limpiarDeepLinkPedido(): void {
  if (typeof location === 'undefined') return
  const id = pedidoIdDesdeBusqueda(location.search)
  if (!id) return
  const url = limpiarPedidoEnUrl(location.pathname + location.search)
  history.replaceState(history.state, '', url)
  enfocarPedidoPestana(id)
}

export function initPedidosPestana(): void {
  if (started) return
  started = true
  watch(
    () => auth.value,
    (a) => {
      if (a === 'ready') {
        void refrescarPedidosPestana()
        limpiarDeepLinkPedido()
      }
    },
    { immediate: true },
  )
  watch(avisoEvent, (e) => e && auth.value === 'ready' && void refrescarPedidosPestana())
  watch(pedidoPestanaEvent, (e) => {
    if (!e || auth.value !== 'ready') return
    aplicarPedidoPestanaSse(e.id, e.estado)
  })
  watch(
    () => boardState.value.board,
    () => {
      cancelarTimerTablero()
      timerTablero = setTimeout(() => {
        timerTablero = null
        // Todas: aprobar exige la huella de la última vista, así que tiene que seguir al tablero.
        const ids = pedidosPestana.items.filter((p) => p.cierre).map((p) => p.id)
        void Promise.all(ids.map((id) => cargarVistaCierre(id)))
      }, DEBOUNCE_TABLERO_MS)
    },
  )
}
