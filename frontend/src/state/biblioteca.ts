import { nextTick, reactive, ref, shallowRef, watch } from 'vue'
import { ApiError, type LibFilters, type LibItem, type LibSession } from '../api/types'
import { chunkIds, emptyFilters, insertNuevos, matchesFilters, mergePage, needsRenewal, parseLibLink, quitadoToast, removeIds } from '../lib/biblioteca'
import { loadBibPrefs, saveBibPrefs } from '../lib/storage'
import { desktop } from '../lib/viewport'
import { isSoft } from '../motion'
import { auth, boardState, getLibrary, getLibraryItem, getLibrarySessions, libraryEvent, quitarLibrary } from './app'
import { findSession } from '../lib/transcript'
import { openSessionChat, openSessionId } from './session'
import { sumarSinVer, verItem, verSesion, type SinVer } from '../lib/bibSinVer'

const PAGE = 60
const prefs = loadBibPrefs()

export const libItems = shallowRef<LibItem[]>([])
export const libFilters = reactive<LibFilters>(emptyFilters())
export const libSessions = shallowRef<LibSession[]>([])
export const lib = reactive({
  loaded: false,
  loading: false,
  loadingMore: false,
  error: '',
  total: 0,
  indexando: false,
  cursor: null as string | null,
  layout: prefs.layout,
  panel: prefs.panel,
  selectedId: null as string | null,
  fullscreen: false,
  newCount: 0,
  /** True while removed cards leave the list: the view animates the reflow. */
  removing: false,
  quitarErr: '',
  aviso: '',
})
/** Section visible (desktop layer or mobile pager page). */
export const libVisible = ref(false)
/** Viewer opened over another screen (chat chip, deep link on mobile): fullscreen on phones, large drawer on desktop. */
export const overlayItem = shallowRef<LibItem | null>(null)
/** Ids being removed: their card plays the exit animation. */
export const libLeaving = ref<string[]>([])
/** Ids that just arrived: their card pulses once. */
export const libFresh = ref<string[]>([])

// Lo que llegó a la Biblioteca y no viste ni ahí ni en el chat de su sesión: es lo que prende el badge.
let sinVer: SinVer = new Map()
function setSinVer(m: SinVer) {
  sinVer = m
  lib.newCount = m.size
}
watch(openSessionId, (sid) => {
  if (sid) setSinVer(verSesion(sinVer, sid))
})
/** App asks to show the section (deep link, chip "Abrir en Biblioteca"). */
export const libRequest = ref<{ n: number } | null>(null)

const itemCache = new Map<string, LibItem | null>()
/** Item by id, fetched once per session of the page; null when it no longer exists. */
export async function cachedLibItem(id: string): Promise<LibItem | null> {
  if (!itemCache.has(id)) itemCache.set(id, await getLibraryItem(id).catch(() => null))
  return itemCache.get(id) ?? null
}

const fetchedAt = new Map<string, number>()
let seq = 0
let freshTimer: ReturnType<typeof setTimeout> | undefined

function remember(items: LibItem[], now = Date.now()) {
  for (const i of items) fetchedAt.set(i.id, now)
}

const snapshot = (): LibFilters => ({ ...libFilters, tipo: [...libFilters.tipo] })

export async function loadLibrary(): Promise<void> {
  const mine = ++seq
  lib.loading = true
  lib.error = ''
  try {
    const page = await getLibrary(snapshot(), null, PAGE)
    if (mine !== seq) return
    remember(page.items)
    libItems.value = page.items
    lib.cursor = page.cursor
    lib.total = page.total
    lib.indexando = page.indexando
    if (!lib.loaded && prefs.visit) setSinVer(sumarSinVer(sinVer, page.items.filter((i) => i.ts > prefs.visit), openSessionId.value))
    lib.loaded = true
  } catch (e) {
    if (mine !== seq) return
    if (!(e instanceof ApiError && e.status === 401)) lib.error = e instanceof ApiError ? e.detail : 'No pude leer la Biblioteca'
  } finally {
    if (mine === seq) lib.loading = false
  }
}

export async function loadMoreLibrary(): Promise<void> {
  if (!lib.cursor || lib.loadingMore || lib.loading) return
  const mine = seq
  lib.loadingMore = true
  try {
    const page = await getLibrary(snapshot(), lib.cursor, PAGE)
    if (mine !== seq) return
    remember(page.items)
    libItems.value = mergePage(libItems.value, page.items)
    lib.cursor = page.cursor
  } catch {
    /* el centinela reintenta en el próximo scroll */
  } finally {
    lib.loadingMore = false
  }
}

export function setFilters(patch: Partial<LibFilters>) {
  Object.assign(libFilters, patch)
  void loadLibrary()
}

export const clearFilters = () => setFilters(emptyFilters())

export async function loadLibrarySessions() {
  try {
    libSessions.value = await getLibrarySessions()
  } catch {
    /* el filtro por sesión queda con lo último que se supo */
  }
}

function persist() {
  saveBibPrefs({ layout: lib.layout, panel: lib.panel, visit: prefs.visit })
}

export function setLayout(l: 'grid' | 'list') {
  lib.layout = l
  persist()
}

export function setPanel(pct: number) {
  lib.panel = Math.min(65, Math.max(40, Math.round(pct)))
  persist()
}

export function markVisited() {
  prefs.visit = new Date().toISOString()
  setSinVer(new Map())
  persist()
}

export async function refreshItem(id: string): Promise<LibItem | null> {
  try {
    const item = await getLibraryItem(id)
    fetchedAt.set(id, Date.now())
    if (libItems.value.some((i) => i.id === id)) libItems.value = libItems.value.map((i) => (i.id === id ? item : i))
    if (overlayItem.value?.id === id) overlayItem.value = item
    return item
  } catch {
    return null
  }
}

/** The viewer URL carries a 30 minute token; ask for a new one when it is about to expire. */
export async function fresh(item: LibItem): Promise<LibItem> {
  const at = fetchedAt.get(item.id)
  if (at !== undefined && !needsRenewal(at, Date.now())) return item
  return (await refreshItem(item.id)) ?? item
}

export const selected = () => libItems.value.find((i) => i.id === lib.selectedId) ?? null

export async function selectItem(id: string | null) {
  lib.selectedId = id
  if (!id) {
    lib.fullscreen = false
    return
  }
  if (!libItems.value.some((i) => i.id === id)) {
    const item = await refreshItem(id)
    if (item && lib.selectedId === id) libItems.value = insertNuevos(libItems.value, [item])
    else if (!item) lib.selectedId = null
  }
}

// ---------- quitar ----------
const EXIT_MS = 300

/** Quita ítems de la Biblioteca (índice y copias propias; los archivos originales no se tocan). */
export async function quitarItems(ids: string[]): Promise<boolean> {
  const wanted = [...new Set(ids)]
  if (!wanted.length) return false
  try {
    for (const part of chunkIds(wanted)) await quitarLibrary(part)
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401)) lib.quitarErr = 'No pude quitarlo, probá de nuevo'
    return false
  }
  libLeaving.value = wanted
  await new Promise((r) => setTimeout(r, isSoft() ? 60 : EXIT_MS))
  const before = libItems.value.length
  lib.removing = true
  libItems.value = removeIds(libItems.value, wanted)
  lib.total = Math.max(0, lib.total - (before - libItems.value.length))
  libLeaving.value = []
  for (const id of wanted) {
    itemCache.delete(id)
    fetchedAt.delete(id)
  }
  if (lib.selectedId && wanted.includes(lib.selectedId)) {
    lib.selectedId = null
    lib.fullscreen = false
  }
  if (overlayItem.value && wanted.includes(overlayItem.value.id)) closeOverlay()
  lib.aviso = quitadoToast(wanted.length)
  setTimeout(() => {
    if (lib.aviso === quitadoToast(wanted.length)) lib.aviso = ''
  }, 2000)
  void loadLibrarySessions()
  await nextTick()
  lib.removing = false
  return true
}

// ---------- viewer over another screen ----------
let overlayPushed = false

export async function openOverlay(id: string) {
  setSinVer(verItem(sinVer, id))
  try {
    const item = await getLibraryItem(id)
    fetchedAt.set(id, Date.now())
    overlayItem.value = item
    if (!overlayPushed) {
      history.pushState({ ...(history.state ?? {}), orqLib: id }, '')
      overlayPushed = true
    }
  } catch (e) {
    if (!(e instanceof ApiError && e.status === 401)) lib.aviso = 'Eso ya no está en la Biblioteca'
  }
}

export function closeOverlay() {
  if (!overlayItem.value) return
  overlayItem.value = null
  if (overlayPushed) {
    overlayPushed = false
    if (history.state?.orqLib) history.back()
  }
}

export function openInLibrary(id: string) {
  overlayItem.value = null
  overlayPushed = false
  libRequest.value = { n: Date.now() }
  void selectItem(id)
}

/** Ir a la sesión que generó el ítem. */
export function goToSession(item: LibItem): boolean {
  if (!findSession(boardState.value.board, item.session_id)) {
    lib.aviso = 'Esa sesión ya no está abierta'
    if (desktop.value) setFilters({ session: item.session_id })
    return false
  }
  overlayItem.value = null
  overlayPushed = false
  libVisible.value = false
  openSessionChat(item.session_id)
  return true
}

// ---------- SSE ----------
async function onNuevos(ids: string[]) {
  const got = await Promise.allSettled(ids.map((id) => getLibraryItem(id)))
  const items = got.flatMap((r) => (r.status === 'fulfilled' ? [r.value] : []))
  if (!items.length) return
  remember(items)
  const known = new Set(libItems.value.map((i) => i.id))
  const added = items.filter((i) => !known.has(i.id) && matchesFilters(i, libFilters))
  if (lib.loaded) {
    libItems.value = insertNuevos(libItems.value, items.filter((i) => matchesFilters(i, libFilters)))
    lib.total += added.length
  }
  if (!libVisible.value) setSinVer(sumarSinVer(sinVer, items.filter((i) => !known.has(i.id)), openSessionId.value))
  libFresh.value = items.map((i) => i.id)
  clearTimeout(freshTimer)
  freshTimer = setTimeout(() => (libFresh.value = []), 2600)
  void loadLibrarySessions()
}

watch(libraryEvent, (e) => e && void onNuevos(e.ids))

// ---------- deep link / lifecycle ----------
export function initLibraryNav(): boolean {
  const link = parseLibLink(location.search)
  if (!link) return false
  const params = new URLSearchParams(location.search)
  params.delete('biblioteca')
  const query = params.toString()
  history.replaceState(history.state, '', location.pathname + (query ? `?${query}` : ''))
  libRequest.value = { n: Date.now() }
  if (link.id) void (desktop.value ? selectItem(link.id) : openOverlay(link.id))
  return true
}

window.addEventListener('popstate', () => {
  if (overlayItem.value && !history.state?.orqLib) {
    overlayItem.value = null
    overlayPushed = false
  }
})

watch(auth, (a) => {
  if (a === 'ready' && !lib.loaded) {
    void loadLibrary()
    void loadLibrarySessions()
  }
  if (a === 'login') {
    libItems.value = []
    libSessions.value = []
    lib.loaded = false
    lib.selectedId = null
    overlayItem.value = null
  }
})
