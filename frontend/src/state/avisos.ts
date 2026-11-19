import { reactive, watch } from 'vue'
import { ApiError, type Aviso, type FiltroAvisos } from '../api/types'
import { coincideAviso, destinoDeAviso, mezclarAvisos, tagsCerrables } from '../lib/avisos'
import { hastaMarcarLeido } from '../lib/avisosEntrada'
import { estaALaVista } from '../lib/aLaVista'
import { desktop } from '../lib/viewport'
import { actualizarBadge, cerrarNotificaciones } from '../lib/notificaciones'
import { auth, avisoEvent, avisosLeidosEvent, viewRequest, getAvisos, marcarAvisosDe, marcarAvisosLeidos } from './app'
import { pushState } from './push'
import { openSessionChat, sesionAtendida } from './session'
import { openTerminal, openTerminalId } from './terminales'
import { irAMr, mrs, mrsVisible } from './mrs'
import { piezas } from '../piezas'
const PAGE = 50

const avisosDePiezas = () => piezas().flatMap((p) => (p.avisos ? [p.avisos] : []))


export const av = reactive({
  open: false,
  loading: false,
  loadingMore: false,
  loaded: false,
  error: '',
  items: [] as Aviso[],
  hayMas: false,
  noLeidos: 0,
  leidosHasta: 0,
  /** Lo que estaba sin leer cuando se abrió el panel: se marca como "nuevo" mientras está abierto. */
  nuevosDesde: 0,
})

let seq = 0

export async function refrescarAvisos(): Promise<void> {
  const mine = ++seq
  if (!av.loaded) av.loading = true
  try {
    const page = await getAvisos(PAGE)
    if (mine !== seq) return
    av.items = mezclarAvisos(av.items, page.items)
    if (!av.loaded || page.items.length >= av.items.length) av.hayMas = page.hayMas
    av.noLeidos = page.noLeidos
    av.leidosHasta = page.leidosHasta
    av.loaded = true
    av.error = ''
    const tags = tagsCerrables(av.items, av.leidosHasta)
    if (tags.length) void cerrarNotificaciones({ tags })
  } catch (e) {
    if (mine !== seq) return
    if (!av.loaded) av.error = e instanceof ApiError ? e.message : 'No pude leer los avisos'
  } finally {
    if (mine === seq) av.loading = false
  }
}

export async function masAvisos(): Promise<void> {
  const last = av.items[av.items.length - 1]
  if (!last || !av.hayMas || av.loadingMore) return
  av.loadingMore = true
  try {
    const page = await getAvisos(PAGE, last.id)
    av.items = mezclarAvisos(av.items, page.items)
    av.hayMas = page.hayMas
  } catch {
    /* el botón sigue ahí para reintentar */
  } finally {
    av.loadingMore = false
  }
}

export async function marcarTodoLeido(): Promise<void> {
  await marcarLeidoHasta(hastaMarcarLeido(av.leidosHasta, av.items))
}

async function marcarLeidoHasta(top: number): Promise<void> {
  if (!top || !av.noLeidos) return
  const antes = av.noLeidos
  av.noLeidos = 0
  av.leidosHasta = top
  try {
    av.noLeidos = await marcarAvisosLeidos(top, pushState.endpoint || undefined)
  } catch {
    av.noLeidos = antes
    av.leidosHasta = Math.min(av.leidosHasta, top - 1)
  }
}

export async function abrirAvisos(): Promise<void> {
  av.open = true
  av.nuevosDesde = av.leidosHasta
  await refrescarAvisos()
  if (av.open) {
    av.nuevosDesde = av.leidosHasta
    await marcarTodoLeido()
  }
}

export function cerrarAvisos(): void {
  av.open = false
}

const sinLeer = (a: Aviso) => !a.leido && a.id > av.leidosHasta

/** Al mirar un destino sus avisos dejan de contar y se cierran sus notificaciones del sistema. */
export async function marcarDestino(f: FiltroAvisos): Promise<void> {
  void cerrarNotificaciones(f)
  const mios = av.items.filter((a) => sinLeer(a) && coincideAviso(a, f))
  if (av.loaded && !mios.length) return
  for (const a of mios) a.leido = true
  av.noLeidos = Math.max(0, av.noLeidos - mios.length)
  try {
    av.noLeidos = await marcarAvisosDe(f, pushState.endpoint || undefined)
  } catch {
    /* el contador se corrige en el próximo refresco */
  }
}

function destinosAbiertos(): FiltroAvisos[] {
  const out: FiltroAvisos[] = []
  if (openTerminalId.value) out.push({ pane_id: openTerminalId.value })
  for (const p of avisosDePiezas()) if (p.abierto()) out.push({ kind: p.kind })
  if (mrsVisible.value && mrs.sel) out.push({ mr: mrs.sel })
  return out
}

const aLaVista = () => estaALaVista(typeof document === 'undefined' ? undefined : document, desktop.value)

async function marcarAbiertos(): Promise<void> {
  if (auth.value !== 'ready' || !aLaVista()) return
  for (const f of destinosAbiertos()) await marcarDestino(f)
}

async function refrescarAlEntrar(): Promise<void> {
  if (auth.value !== 'ready') return
  const mine = ++seq
  if (!av.loaded) av.loading = true
  try {
    const page = await getAvisos(PAGE)
    if (mine !== seq) return
    av.items = mezclarAvisos(av.items, page.items)
    if (!av.loaded || page.items.length >= av.items.length) av.hayMas = page.hayMas
    av.noLeidos = page.noLeidos
    av.leidosHasta = page.leidosHasta
    av.loaded = true
    av.error = ''
    const tags = tagsCerrables(av.items, av.leidosHasta)
    if (tags.length) void cerrarNotificaciones({ tags })
    const top = hastaMarcarLeido(av.leidosHasta, av.items)
    if (mine === seq && page.noLeidos) await marcarLeidoHasta(top)
  } catch (e) {
    if (mine !== seq) return
    if (!av.loaded) av.error = e instanceof ApiError ? e.message : 'No pude leer los avisos'
  } finally {
    if (mine === seq) av.loading = false
  }
}

async function avisoNuevo(): Promise<void> {
  const top = Math.max(0, ...av.items.map((a) => a.id))
  await refrescarAvisos()
  await marcarAbiertos()
  if (!aLaVista()) return
  const nuevo = av.items.find((a) => a.id > top && a.kind !== 'test' && !a.prueba && sinLeer(a))
  if (!nuevo || !top) return
  /* la campana sacude y suma el contador vía av.noLeidos */
}

export function irAAviso(a: Aviso): void {
  const deP = avisosDePiezas()
  const d = destinoDeAviso(a, deP.map((p) => p.kind))
  av.open = false
  if (d.tipo === 'sesion') openSessionChat(d.id)
  else if (d.tipo === 'tablero') {
    void marcarDestino({ kind: a.kind })
    viewRequest.value = { view: 'board', n: Date.now() }
  } else if (d.tipo === 'terminal') openTerminal(d.id)
  else if (d.tipo === 'mr') irAMr(d.ref)
  else if (d.tipo === 'pieza') deP.find((p) => p.kind === d.kind)?.ir(a)
}

let started = false

/** Sin polling: se refresca al entrar, al volver la app a primer plano y cuando el servidor avisa de uno nuevo. */
export function initAvisos(): void {
  if (started) return
  started = true
  watch(() => auth.value, (a) => a === 'ready' && void refrescarAlEntrar(), { immediate: true })
  watch(avisoEvent, (e) => e && auth.value === 'ready' && void avisoNuevo())
  watch(avisosLeidosEvent, (e) => {
    if (!e || auth.value !== 'ready') return
    if (e.tags.length) void cerrarNotificaciones({ tags: e.tags })
    void refrescarAvisos()
  })
  watch([() => auth.value, openTerminalId, () => avisosDePiezas().map((p) => p.abierto()), () => mrs.sel], () => void marcarAbiertos(), { immediate: true })
  watch(sesionAtendida, (v) => v?.id && void marcarDestino({ session_id: v.id }))
  watch(() => av.noLeidos, (n) => void actualizarBadge(n), { immediate: true })
  const alVolverVisible = () => {
    if (auth.value === 'ready' && aLaVista()) void refrescarAlEntrar().then(marcarAbiertos)
  }
  const alFoco = () => {
    if (auth.value === 'ready' && aLaVista()) void marcarAbiertos()
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', alVolverVisible)
    window.addEventListener('focus', alFoco)
  }
}
