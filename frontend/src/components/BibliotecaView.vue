<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { LibItem } from '../api/types'
import { groupByDay, groupIndex, isFiltering, isTyping, KIND_LABEL, neighbours, pathLabel, pickIds, quitarLabel, safeClaudeUrl, shortcutFor, TYPE_GROUPS, type ShortcutAction } from '../lib/biblioteca'
import { copyText } from '../lib/clipboard'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { desktop } from '../lib/viewport'
import { Flip, finePointer, gsap, haptic, isSoft, useGsap } from '../motion'
import {
  clearFilters, goToSession, lib, libFilters, libFresh, libItems, libLeaving, libSessions, loadLibrary, loadMoreLibrary, markVisited,
  quitarItems, selectItem, setFilters, setLayout, setPanel,
} from '../state/biblioteca'
import BibCard from './BibCard.vue'
import BibQuitarSheet from './BibQuitarSheet.vue'
import BibViewer from './BibViewer.vue'
import Icon from './Icon.vue'
import ViewFrame from './ViewFrame.vue'
import EmptyState from './EmptyState.vue'
import SkeletonList from './SkeletonList.vue'

const props = defineProps<{ visible: boolean }>()

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const scroller = ref<HTMLElement | null>(null)
const sentinel = ref<HTMLElement | null>(null)
const searchEl = ref<HTMLInputElement | null>(null)
const viewerRef = ref<InstanceType<typeof BibViewer> | null>(null)

const items = libItems
const groups = computed(() => groupByDay(items.value, Date.now()))
const flat = computed(() => groups.value.flatMap((g) => g.items))
const index = (it: LibItem) => flat.value.indexOf(it)
const selected = computed(() => items.value.find((i) => i.id === lib.selectedId) ?? null)
const near = computed(() => (selected.value ? neighbours(items.value, selected.value.id) : { prev: null, next: null }))
const filtering = computed(() => isFiltering(libFilters))
const popActive = computed(() => !!libFilters.session || !!libFilters.desde || !!libFilters.hasta)
const activeGroup = computed(() => groupIndex(libFilters.tipo))
const count = computed(() => `${lib.total} ${lib.total === 1 ? 'resultado' : 'resultados'}`)

// ---------- search ----------
const q = ref(libFilters.q)
let qTimer: ReturnType<typeof setTimeout> | undefined
function onSearch() {
  clearTimeout(qTimer)
  qTimer = setTimeout(() => setFilters({ q: q.value }), 260)
}
watch(() => libFilters.q, (v) => (q.value = v))
const searchOpen = ref(false)
async function openSearch() {
  searchOpen.value = true
  await nextTick()
  searchEl.value?.focus()
}

function pickGroup(i: number) {
  haptic(5)
  setFilters({ tipo: [...TYPE_GROUPS[i].tipo] })
}

// ---------- focus / selection ----------
const focusIdx = ref(0)
const cols = ref(1)

function cardEl(i: number): HTMLElement | null {
  return scroller.value?.querySelector<HTMLElement>(`[data-idx="${i}"]`) ?? null
}

function moveFocus(i: number) {
  if (i < 0 || i >= flat.value.length) return
  focusIdx.value = i
  nextTick(() => {
    const el = cardEl(i)
    el?.focus({ preventScroll: true })
    el?.scrollIntoView({ block: 'nearest', behavior: isSoft() ? 'auto' : 'smooth' })
  })
}

function moveVertical(dir: 1 | -1) {
  const cur = cardEl(focusIdx.value)
  if (!cur) return moveFocus(0)
  const r = cur.getBoundingClientRect()
  let best = -1
  let bestScore = Infinity
  scroller.value?.querySelectorAll<HTMLElement>('[data-idx]').forEach((el) => {
    const b = el.getBoundingClientRect()
    const dy = (b.top - r.top) * dir
    if (dy < 6) return
    const score = dy * 4 + Math.abs(b.left - r.left)
    if (score < bestScore) {
      bestScore = score
      best = Number(el.dataset.idx)
    }
  })
  if (best >= 0) moveFocus(best)
}

function open(it: LibItem) {
  focusIdx.value = index(it)
  void selectItem(it.id)
}

async function openFull(it: LibItem) {
  open(it)
  if (!desktop.value) return
  await nextTick()
  await new Promise((r) => requestAnimationFrame(r))
  viewerRef.value?.toggleFullscreen()
}

function step(dir: 1 | -1) {
  const n = dir > 0 ? near.value.next : near.value.prev
  if (!n) return
  haptic(5)
  void selectItem(n.id)
  focusIdx.value = flat.value.findIndex((i) => i.id === n.id)
  if (dir > 0 && !near.value.next?.id) void loadMoreLibrary()
}

function closeViewer() {
  haptic(8)
  void selectItem(null)
}

// ---------- quitar: confirmación, selección múltiple ----------
const ask = ref<string[] | null>(null)
const selecting = ref(false)
const picked = ref<string[]>([])
const lastPick = ref<string | null>(null)
const nameOf = (it: LibItem) => it.title || it.nombre || KIND_LABEL[it.kind]
const askName = computed(() => {
  const one = ask.value?.length === 1 ? items.value.find((i) => i.id === ask.value![0]) : null
  return one ? nameOf(one) : ''
})

function askQuitar(ids: string[]) {
  if (ids.length) ask.value = ids
}

async function confirmQuitar() {
  const ids = ask.value
  ask.value = null
  if (!ids) return
  haptic(8)
  if (await quitarItems(ids)) {
    picked.value = picked.value.filter((id) => !ids.includes(id))
    if (selecting.value && !picked.value.length) selecting.value = false
    const n = Math.min(focusIdx.value, flat.value.length - 1)
    focusIdx.value = Math.max(0, n)
  }
}

function toggleSelecting(on = !selecting.value) {
  haptic(5)
  selecting.value = on
  picked.value = []
  lastPick.value = null
  if (on) {
    hoverOut()
    if (selected.value) void selectItem(null)
  }
}

function pick(it: LibItem, range = false) {
  focusIdx.value = index(it)
  picked.value = pickIds(picked.value, flat.value.map((i) => i.id), it.id, lastPick.value, range)
  lastPick.value = it.id
}

function pickAll() {
  const all = flat.value.map((i) => i.id)
  picked.value = picked.value.length === all.length ? [] : all
}

watch(flat, (rows) => {
  const have = new Set(rows.map((i) => i.id))
  if (picked.value.some((id) => !have.has(id))) picked.value = picked.value.filter((id) => have.has(id))
})

// Reflow suave cuando se quitan tarjetas.
let flipState: ReturnType<typeof Flip.getState> | null = null
watch(libItems, () => {
  if (!lib.removing || isSoft() || !scroller.value) return
  flipState = Flip.getState(scroller.value.querySelectorAll('.card'))
}, { flush: 'pre' })
watch(libItems, () => {
  const st = flipState
  flipState = null
  if (st) nextTick(() => run(() => Flip.from(st, { duration: 0.5, ease: 'power3.inOut', absolute: false, onComplete: measureCols })))
}, { flush: 'post' })

// ---------- hover preview (one at a time) ----------
const previewId = ref('')
let hoverTimer: ReturnType<typeof setTimeout> | undefined
function hoverIn(it: LibItem) {
  clearTimeout(hoverTimer)
  if (isSoft() || !finePointer() || !desktop.value || it.kind !== 'html' || !it.servible) return
  hoverTimer = setTimeout(() => (previewId.value = it.id), 500)
}
function hoverOut() {
  clearTimeout(hoverTimer)
  previewId.value = ''
}

// ---------- layout toggle with Flip ----------
function toggleLayout(l: 'grid' | 'list' = lib.layout === 'grid' ? 'list' : 'grid') {
  if (l === lib.layout) return
  hoverOut()
  const els = scroller.value ? [...scroller.value.querySelectorAll('.card')] : []
  const state = !isSoft() && els.length ? Flip.getState(els) : null
  setLayout(l)
  nextTick(() => {
    if (state) run(() => Flip.from(state, { duration: 0.5, ease: 'power3.inOut', stagger: 0.008, absolute: false, onComplete: measureCols }))
    else measureCols()
  })
}

function measureCols() {
  const g = scroller.value?.querySelector('.grid')
  cols.value = g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 1
}

// ---------- entrance on (re)load ----------
async function enter() {
  await nextTick()
  measureCols()
  const els = scroller.value ? [...scroller.value.querySelectorAll<HTMLElement>('.card')].slice(0, 28) : []
  if (!els.length) return
  if (isSoft()) run(() => gsap.fromTo(els, { opacity: 0 }, { opacity: 1, duration: 0.15, clearProps: 'opacity' }))
  else run(() => gsap.fromTo(els, { opacity: 0, y: 16, scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: 0.55, ease: 'power3.out', stagger: 0.03, clearProps: 'transform,opacity' }))
}
watch(() => lib.loading, (on, was) => !on && was && props.visible && enter())
watch(() => props.visible, (v) => {
  if (!v) {
    hoverOut()
    return
  }
  markVisited()
  enter()
})

// ---------- infinite scroll ----------
let io: IntersectionObserver | null = null
function watchSentinel() {
  io?.disconnect()
  if (sentinel.value && scroller.value) {
    io = new IntersectionObserver((e) => e[0].isIntersecting && void loadMoreLibrary(), { root: scroller.value, rootMargin: '480px' })
    io.observe(sentinel.value)
  }
}
watch(sentinel, watchSentinel)

// ---------- panel resize ----------
const resizing = ref(false)
function startResize(e: PointerEvent) {
  const host = root.value
  if (!host) return
  resizing.value = true
  const target = e.currentTarget as HTMLElement
  target.setPointerCapture(e.pointerId)
  const move = (ev: PointerEvent) => {
    const r = host.getBoundingClientRect()
    setPanel(((r.right - ev.clientX) / r.width) * 100)
  }
  const up = () => {
    resizing.value = false
    target.removeEventListener('pointermove', move)
    target.removeEventListener('pointerup', up)
    target.removeEventListener('pointercancel', up)
  }
  target.addEventListener('pointermove', move)
  target.addEventListener('pointerup', up)
  target.addEventListener('pointercancel', up)
}
function resizeKey(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') setPanel(lib.panel + 2)
  else if (e.key === 'ArrowRight') setPanel(lib.panel - 2)
  else return
  e.preventDefault()
}

// ---------- quick look + help ----------
const quick = ref(false)
const help = ref(false)
const filtersOpen = ref(false)
const filtersPanel = ref<HTMLElement | null>(null)
useSheetSwipe(filtersPanel, () => {
  filtersOpen.value = false
})
const datesOpen = ref(false)
const datesWrap = ref<HTMLElement | null>(null)
function onDocDown(e: PointerEvent) {
  if (datesOpen.value && !datesWrap.value?.contains(e.target as Node)) datesOpen.value = false
}
const lookItem = computed(() => selected.value ?? flat.value[focusIdx.value] ?? null)
let spaceAt = 0

// ---------- keyboard ----------
function act(a: ShortcutAction, e: KeyboardEvent): boolean {
  const it = selected.value ?? flat.value[focusIdx.value] ?? null
  switch (a) {
    case 'search': searchOpen.value = true; nextTick(() => searchEl.value?.focus()); return true
    case 'left': moveFocus(focusIdx.value - 1); return true
    case 'right': moveFocus(focusIdx.value + 1); return true
    case 'up': moveVertical(-1); return true
    case 'down': moveVertical(1); return true
    case 'quitar': {
      if (selecting.value) askQuitar(picked.value)
      else if (it) askQuitar([it.id])
      return !!it
    }
    case 'enter': {
      const cur = flat.value[focusIdx.value]
      if (!cur) return false
      if (selecting.value) {
        pick(cur)
        return true
      }
      if (selected.value) viewerRef.value?.toggleFullscreen()
      else open(cur)
      return true
    }
    case 'quick':
      if (selecting.value) {
        const cur = flat.value[focusIdx.value]
        if (cur && !e.repeat) pick(cur, e.shiftKey)
        return true
      }
      if (e.repeat) return true
      if (quick.value) quick.value = false
      else if (lookItem.value) {
        quick.value = true
        spaceAt = Date.now()
      }
      return true
    case 'prev': step(-1); return true
    case 'next': step(1); return true
    case 'fullscreen':
      if (!selected.value && it) openFull(it)
      else viewerRef.value?.toggleFullscreen()
      return true
    case 'escape':
      if (ask.value) ask.value = null
      else if (help.value) help.value = false
      else if (selecting.value) toggleSelecting(false)
      else if (quick.value) quick.value = false
      else if (selected.value) closeViewer()
      else if (libFilters.q) setFilters({ q: '' })
      else return false
      if (isTyping(document.activeElement)) (document.activeElement as HTMLElement).blur()
      return true
    case 'claude': {
      const url = it ? safeClaudeUrl(it.url) : ''
      if (url) window.open(url, '_blank', 'noopener,noreferrer')
      return !!url
    }
    case 'session': if (it) goToSession(it); return !!it
    case 'copy':
      if (it) {
        void copyText(pathLabel(it)).then((ok) => {
          if (ok) lib.aviso = 'Ruta copiada'
          else lib.aviso = 'No se pudo copiar la ruta'
        })
      }
      return !!it
    case 'reload': viewerRef.value?.reload(); return !!selected.value
    case 'toggleView': toggleLayout(); return true
    case 'help': help.value = !help.value; return true
    default:
      if (a.startsWith('type')) pickGroup(Number(a.slice(4)) - 1)
      return true
  }
}

function onKey(e: KeyboardEvent) {
  if (!props.visible || !desktop.value || ask.value) return
  const a = shortcutFor(e, isTyping(document.activeElement))
  if (a && act(a, e)) e.preventDefault()
}
function onKeyUp(e: KeyboardEvent) {
  if (e.key === ' ' && quick.value && Date.now() - spaceAt > 400) quick.value = false
}

// ---------- mobile: fullscreen viewer, swipe, history ----------
const sheet = ref<HTMLElement | null>(null)
let pushed = false
watch(() => lib.selectedId, (id) => {
  if (desktop.value) return
  if (id && !pushed) {
    history.pushState({ ...(history.state ?? {}), orqLibView: true }, '')
    pushed = true
  } else if (!id && pushed) {
    pushed = false
    if (history.state?.orqLibView) history.back()
  }
})
function onPop() {
  if (!desktop.value && lib.selectedId && !history.state?.orqLibView) {
    pushed = false
    void selectItem(null)
  }
}

const EDGE = 24
let g: { id: number; x0: number; y0: number; lock: 'x' | 'y' | null; t0: number } | null = null
function swipeAllowed(e: PointerEvent): boolean {
  const el = sheet.value
  if (!el) return false
  const r = el.getBoundingClientRect()
  const x = e.clientX - r.left
  const y = e.clientY - r.top
  const k = selected.value?.kind
  if (k === 'html' || k === 'svg' || k === 'image' || k === 'gif') return y < 64 || x < EDGE || x > r.width - EDGE
  return true
}
function sDown(e: PointerEvent) {
  if (desktop.value || e.pointerType === 'mouse' || !swipeAllowed(e)) return
  if (sheet.value) gsap.killTweensOf(sheet.value)
  g = { id: e.pointerId, x0: e.clientX, y0: e.clientY, lock: null, t0: e.timeStamp }
}
function sMove(e: PointerEvent) {
  if (!g || e.pointerId !== g.id || !sheet.value) return
  const dx = e.clientX - g.x0
  const dy = e.clientY - g.y0
  if (!g.lock) {
    if (Math.abs(dx) < 10 && Math.abs(dy) < 10) return
    g.lock = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
    if (g.lock === 'y' && dy < 0) {
      g = null
      return
    }
    sheet.value.setPointerCapture(e.pointerId)
  }
  if (g.lock === 'x') gsap.set(sheet.value, { x: dx, opacity: 1 - Math.min(0.5, Math.abs(dx) / 700) })
  else gsap.set(sheet.value, { y: Math.max(0, dy), scale: 1 - Math.min(0.08, dy / 2400), opacity: 1 - Math.min(0.5, dy / 600) })
}
function sUp(e: PointerEvent) {
  if (!g || e.pointerId !== g.id || !sheet.value) return
  const st = g
  g = null
  const el = sheet.value
  const settle = () => gsap.to(el, { x: 0, y: 0, scale: 1, opacity: 1, duration: isSoft() ? 0.1 : 0.45, ease: 'expo.out', clearProps: 'transform,opacity' })
  if (e.type === 'pointercancel') {
    if (st.lock) settle()
    return
  }
  const dx = e.clientX - st.x0
  const dy = e.clientY - st.y0
  const v = Math.abs(st.lock === 'x' ? dx : dy) / Math.max(1, e.timeStamp - st.t0)
  if (st.lock === 'y' && (dy > 110 || v > 0.6)) {
    closeViewer()
    gsap.set(el, { clearProps: 'transform,opacity' })
  } else if (st.lock === 'x' && (Math.abs(dx) > 90 || v > 0.5)) {
    const n = dx < 0 ? near.value.next : near.value.prev
    if (n) {
      haptic(6)
      void selectItem(n.id)
      gsap.fromTo(el, { x: dx < 0 ? 60 : -60, opacity: 0.4 }, { x: 0, opacity: 1, duration: isSoft() ? 0.1 : 0.4, ease: 'power3.out', clearProps: 'transform,opacity' })
    } else settle()
  } else if (st.lock) settle()
}

onMounted(() => {
  window.addEventListener('keydown', onKey)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('popstate', onPop)
  document.addEventListener('pointerdown', onDocDown)
  watchSentinel()
  if (!lib.loaded && !lib.loading) void loadLibrary()
  else if (props.visible) enter()
  if (scroller.value) {
    ro = new ResizeObserver(measureCols)
    ro.observe(scroller.value)
  }
})
let ro: ResizeObserver | null = null
onBeforeUnmount(() => {
  ro?.disconnect()
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('popstate', onPop)
  document.removeEventListener('pointerdown', onDocDown)
  io?.disconnect()
  clearTimeout(qTimer)
  clearTimeout(hoverTimer)
})

const SHORTCUTS: [string, string][] = [
  ['/', 'Buscar'], ['← → ↑ ↓  ·  h j k l', 'Mover la selección'], ['Enter', 'Abrir; con el panel abierto, pantalla completa'],
  ['Espacio', 'Vista rápida'], ['[  ]', 'Anterior / siguiente'], ['F', 'Pantalla completa'], ['Esc', 'Salir, cerrar, limpiar búsqueda'],
  ['Supr', 'Quitar de la Biblioteca (pide confirmación)'], ['O', 'Abrir en claude.ai'], ['S', 'Ir a la sesión'], ['C', 'Copiar la ruta'], ['R', 'Recargar el visor'],
  ['1 … 6', 'Todo · Páginas · Imágenes · PDF · Diagramas · Otros'], ['G', 'Grilla / lista'], ['?', 'Esta hoja'],
]
</script>

<template>
  <div ref="root" class="bib" :class="{ desktop, 'has-viewer': !!selected, resizing, list: lib.layout === 'list' }" :style="{ '--panel': `${lib.panel}%` }">
    <div class="main" :inert="!desktop && !!selected">
      <ViewFrame class="bib-vf" :title="desktop || !searchOpen ? 'Biblioteca' : undefined" aria-label="Biblioteca">
        <template v-if="desktop || !searchOpen" #meta>
          <span class="count mono" aria-live="polite">{{ count }}</span>
          <span v-if="lib.indexando" class="indexing"><i class="spin" /> Indexando sesiones</span>
        </template>
        <template #toolbar>
        <label class="search" :class="{ open: desktop || searchOpen }">
          <button v-if="!desktop && !searchOpen" type="button" class="s-ic" aria-label="Buscar" @click="openSearch"><Icon name="search" :size="17" /></button>
          <template v-else>
            <Icon name="search" :size="15" />
            <input
              ref="searchEl"
              v-model="q"
              type="search"
              placeholder="Buscar páginas, imágenes, sesiones…"
              aria-label="Buscar en la Biblioteca"
              enterkeyhint="search"
              @input="onSearch"
              @blur="!q && !desktop && (searchOpen = false)"
            />
            <kbd v-if="desktop && !q">/</kbd>
          </template>
        </label>
        <div class="types" role="tablist" aria-label="Tipo">
          <button
            v-for="(t, i) in TYPE_GROUPS"
            :key="t.key"
            role="tab"
            class="type"
            :class="{ on: i === activeGroup }"
            :aria-selected="i === activeGroup"
            :title="desktop ? `${t.label} (${t.key})` : t.label"
            @click="pickGroup(i)"
          >
            {{ t.label }}
          </button>
        </div>
        <div v-if="desktop" class="filters">
          <div ref="datesWrap" class="dates-wrap">
            <button type="button" class="fbtn" :class="{ on: datesOpen || popActive }" aria-haspopup="dialog" :aria-expanded="datesOpen" @click="datesOpen = !datesOpen">
              <Icon name="target" :size="14" /> Filtros<i v-if="popActive" class="pip" />
            </button>
            <Transition name="drop">
              <div v-if="datesOpen" class="pop" role="dialog" aria-label="Filtros" @keydown.esc.stop="datesOpen = false">
                <label class="wide">Sesión
                  <select :value="libFilters.session" @change="setFilters({ session: ($event.target as HTMLSelectElement).value })">
                    <option value="">Todas las sesiones</option>
                    <option v-for="s in libSessions" :key="s.session_id" :value="s.session_id">{{ s.titulo }} ({{ s.n }})</option>
                  </select>
                </label>
                <label>Desde<input type="date" :value="libFilters.desde" @change="setFilters({ desde: ($event.target as HTMLInputElement).value })" /></label>
                <label>Hasta<input type="date" :value="libFilters.hasta" @change="setFilters({ hasta: ($event.target as HTMLInputElement).value })" /></label>
              </div>
            </Transition>
          </div>
          <button class="clear" :class="{ idle: !filtering }" :disabled="!filtering" :tabindex="filtering ? 0 : -1" @click="clearFilters">Limpiar</button>
        </div>
        <button v-else class="filter-btn" :class="{ on: !!libFilters.session || !!libFilters.desde || !!libFilters.hasta }" aria-label="Filtros" @click="filtersOpen = true">
          <Icon name="dots" :size="17" />
        </button>
        <div v-if="desktop" class="layout" role="group" aria-label="Vista">
          <button :class="{ on: lib.layout === 'grid' }" aria-label="Grilla" title="Grilla (G)" @click="toggleLayout('grid')"><Icon name="grid" :size="15" /></button>
          <button :class="{ on: lib.layout === 'list' }" aria-label="Lista" title="Lista (G)" @click="toggleLayout('list')"><Icon name="list" :size="15" /></button>
        </div>
        <button v-if="items.length || selecting" type="button" class="selbtn" :class="{ on: selecting }" :aria-pressed="selecting" :aria-label="selecting ? 'Salir de la selección' : 'Seleccionar'" @click="toggleSelecting()">
          <Icon name="check" :size="15" /><span v-if="desktop">{{ selecting ? 'Listo' : 'Seleccionar' }}</span>
        </button>
        </template>

      <div ref="scroller" class="scroller view-scroll" @scroll.passive="hoverOut">
        <SkeletonList v-if="lib.loading && !items.length" variant="card" :count="8" :rows="1" class="skeletons" />
        <EmptyState v-else-if="lib.error && !items.length" icon="warn" :title="lib.error">
          <template #action>
            <button type="button" class="btn btn-ghost" @click="loadLibrary"><Icon name="refresh" :size="14" /> Reintentar</button>
          </template>
        </EmptyState>
        <EmptyState v-else-if="!items.length && filtering" title="No hay nada con esos filtros.">
          <template #action>
            <button v-if="!desktop" type="button" class="btn btn-ghost" @click="clearFilters">Limpiar filtros</button>
          </template>
        </EmptyState>
        <EmptyState v-else-if="!items.length">
          <template #icon>
            <svg viewBox="0 0 120 90" width="132" aria-hidden="true">
              <rect x="12" y="26" width="46" height="52" rx="8" fill="none" stroke="currentColor" stroke-width="2" opacity=".5" />
              <rect x="34" y="14" width="46" height="52" rx="8" fill="var(--bg)" stroke="currentColor" stroke-width="2" opacity=".8" />
              <rect x="58" y="30" width="46" height="46" rx="8" fill="var(--bg)" stroke="var(--accent)" stroke-width="2.4" />
              <path d="m70 62 10-12 8 8 5-5" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </template>
          Todavía no hay nada. Cuando una sesión publique una página o te mande un archivo, aparece acá.
        </EmptyState>
        <template v-else>
          <section v-for="grp in groups" :key="grp.key" class="day">
            <h3 class="day-h">{{ grp.label }}<span class="mono">{{ grp.items.length }}</span></h3>
            <div class="grid" :class="lib.layout" role="grid" :aria-label="grp.label">
              <BibCard
                v-for="it in grp.items"
                :key="it.id"
                :item="it"
                :layout="lib.layout"
                :index="index(it)"
                :selected="it.id === lib.selectedId"
                :fresh="libFresh.includes(it.id)"
                :preview="previewId === it.id"
                :tab="index(it) === focusIdx"
                :selecting="selecting"
                :checked="picked.includes(it.id)"
                :leaving="libLeaving.includes(it.id)"
                @quitar="askQuitar([it.id])"
                @toggle="pick(it, $event)"
                @open="open(it)"
                @full="openFull(it)"
                @enter="hoverIn(it)"
                @leave="hoverOut"
              />
            </div>
          </section>
          <div ref="sentinel" class="sentinel" aria-hidden="true"><i v-if="lib.loadingMore" class="spin" /></div>
        </template>
      </div>
      <Transition name="selbar">
        <div v-if="selecting" class="selbar" role="toolbar" aria-label="Selección">
          <span class="sel-n mono" aria-live="polite">{{ picked.length }} {{ picked.length === 1 ? 'elegida' : 'elegidas' }}</span>
          <button type="button" class="sel-link" @click="pickAll">{{ picked.length === flat.length && flat.length ? 'Ninguna' : 'Todas' }}</button>
          <button type="button" class="sel-btn" @click="toggleSelecting(false)">Cancelar</button>
          <button type="button" class="sel-btn danger" :disabled="!picked.length" @click="askQuitar(picked)"><Icon name="trash" :size="14" /> {{ quitarLabel(picked.length) }}</button>
        </div>
      </Transition>
      </ViewFrame>
    </div>

    <template v-if="desktop">
      <Transition name="panel">
        <div v-if="selected" class="dim" @click="closeViewer" />
      </Transition>
      <Transition name="panel">
        <div v-if="selected" class="side" :class="{ resizing }">
          <div class="resizer" role="separator" aria-orientation="vertical" aria-label="Ancho del visor" tabindex="0" @pointerdown.prevent="startResize" @keydown="resizeKey" />
          <BibViewer
            ref="viewerRef"
            :item="selected"
            mode="panel"
            :has-prev="!!near.prev"
            :has-next="!!near.next"
            @close="closeViewer"
            @prev="step(-1)"
            @next="step(1)"
            @session="goToSession(selected)"
          />
        </div>
      </Transition>
      <Transition name="fade">
        <div v-if="quick && lookItem" class="quick" @click.self="quick = false">
          <div class="quick-card">
            <BibViewer :item="lookItem" mode="overlay" :has-prev="false" :has-next="false" @close="quick = false" @session="goToSession(lookItem)" @library="quick = false" />
          </div>
        </div>
      </Transition>
      <Transition name="fade">
        <div v-if="help" class="quick" @click.self="help = false">
          <div class="help" role="dialog" aria-label="Atajos de teclado">
            <h3><Icon name="keyboard" :size="16" /> Atajos</h3>
            <dl>
              <template v-for="[k, d] in SHORTCUTS" :key="k"><dt class="mono">{{ k }}</dt><dd>{{ d }}</dd></template>
            </dl>
          </div>
        </div>
      </Transition>
    </template>

    <Teleport v-else to="body">
      <Transition name="mview">
        <div v-if="selected" ref="sheet" class="m-viewer" @pointerdown="sDown" @pointermove="sMove" @pointerup="sUp" @pointercancel="sUp">
          <BibViewer
            ref="viewerRef"
            :item="selected"
            mode="mobile"
            :has-prev="!!near.prev"
            :has-next="!!near.next"
            @close="closeViewer"
            @prev="step(-1)"
            @next="step(1)"
            @session="goToSession(selected)"
          />
        </div>
      </Transition>
      <Transition name="sheet">
        <div v-if="filtersOpen" class="sheet-root sheet-bg" @click.self="filtersOpen = false">
          <div class="sheet-scrim" aria-hidden="true" @click="filtersOpen = false" />
          <div ref="filtersPanel" class="sheet-panel sheet" role="dialog" aria-label="Filtros">
            <i class="sheet-grip" aria-hidden="true" />
            <h3 class="sheet-title">Filtros</h3>
            <label>Sesión
              <select :value="libFilters.session" @change="setFilters({ session: ($event.target as HTMLSelectElement).value })">
                <option value="">Todas las sesiones</option>
                <option v-for="s in libSessions" :key="s.session_id" :value="s.session_id">{{ s.titulo }} ({{ s.n }})</option>
              </select>
            </label>
            <div class="dates">
              <label>Desde<input type="date" :value="libFilters.desde" @change="setFilters({ desde: ($event.target as HTMLInputElement).value })" /></label>
              <label>Hasta<input type="date" :value="libFilters.hasta" @change="setFilters({ hasta: ($event.target as HTMLInputElement).value })" /></label>
            </div>
            <div class="sheet-actions">
              <button type="button" class="btn btn-ghost" @click="clearFilters(); filtersOpen = false">Limpiar</button>
              <button type="button" class="btn btn-primary" @click="filtersOpen = false">Listo</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
    <BibQuitarSheet :open="!!ask" :count="ask?.length ?? 0" :name="askName" @confirm="confirmQuitar" @cancel="ask = null" />
  </div>
</template>

<style scoped>
.bib {
  position: relative;
  height: 100%;
  min-height: 0;
  display: flex;
  background: var(--bg);
}
.main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  transition: filter 0.4s var(--ease-out), opacity 0.4s;
}
.bib-vf {
  flex: 1;
  min-height: 0;
}
.bib-vf :deep(.vf-toolbar) {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  padding-top: 0;
  width: 100%;
}
.bib-vf :deep(.vf-body) {
  flex: 1;
  min-height: 0;
  padding: 0;
  gap: 0;
  overflow: hidden;
}
.bib-vf :deep(.vh-sub),
.bib-vf :deep(.vh-meta) {
  display: flex;
  align-items: baseline;
  gap: 10px;
  flex-wrap: wrap;
}
.count {
  font-size: 11px;
  color: var(--text-4);
}
.indexing {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-3);
}
.search {
  display: flex;
  align-items: center;
  gap: 8px;
  height: 36px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  min-width: 240px;
  flex: 0 1 340px;
  color: var(--text-3);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: box-shadow 0.25s, background 0.25s;
}
.search:focus-within {
  box-shadow: inset 0 0 0 1.5px var(--accent);
  background: var(--surface-2);
}
.search input {
  flex: 1;
  min-width: 0;
  height: 100%;
  font: inherit;
  font-size: var(--t-lg);
  color: var(--text);
  background: none;
  border: 0;
  outline: none;
}
.search kbd,
.help dt {
  font-family: var(--font-mono);
  font-size: var(--t-xs);
}
.search kbd {
  padding: 1px 6px;
  border-radius: 5px;
  color: var(--text-4);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.types {
  display: flex;
  gap: 2px;
  padding: 3px;
  border-radius: var(--r-pill);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
.type {
  height: 28px;
  padding: 0 13px;
  border-radius: var(--r-pill);
  font-size: var(--t-md);
  font-weight: 540;
  color: var(--text-3);
  white-space: nowrap;
  transition: color 0.25s, background 0.3s, scale 0.3s var(--spring);
}
.type:hover {
  color: var(--text);
}
.type.on {
  color: var(--accent-ink);
  background: var(--accent);
}
.type:active {
  scale: var(--press-scale);
}
.filters {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}
select,
input[type='date'] {
  height: 34px;
  padding: 0 10px;
  border-radius: var(--r-md);
  font: inherit;
  font-size: var(--t-md);
  color: var(--text-2);
  background: var(--surface);
  border: 0;
  box-shadow: inset 0 0 0 1px var(--line);
  max-width: 220px;
  min-width: 0;
  color-scheme: inherit;
}
input[type='date'] {
  max-width: 160px;
}
select:focus,
input[type='date']:focus {
  outline: none;
  box-shadow: inset 0 0 0 1.5px var(--accent);
}
.clear {
  font-size: var(--t-md);
  color: var(--accent);
  padding: 0 6px;
  min-width: 52px;
  transition: opacity 0.2s;
}
.clear.idle {
  opacity: 0;
  pointer-events: none;
}
.dates-wrap {
  position: relative;
}
.fbtn {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 34px;
  padding: 0 12px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  color: var(--text-2);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: color 0.2s, background 0.2s, box-shadow 0.2s;
}
.fbtn:hover {
  background: var(--surface-hover);
}
.fbtn.on {
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.pip {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
}
.pop {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  z-index: 8;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  width: 320px;
  padding: 12px;
  border-radius: var(--r-lg);
  background: var(--surface-2);
  box-shadow: var(--shadow-pop), inset 0 0 0 1px var(--line-2);
}
.pop .wide {
  grid-column: 1 / -1;
}
.pop select {
  width: 100%;
  max-width: none;
  box-sizing: border-box;
}
.pop label {
  display: grid;
  gap: 5px;
  min-width: 0;
  font-size: var(--t-sm);
  color: var(--text-3);
}
.pop input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
}
.drop-enter-active { transition: transform 0.4s var(--spring), opacity 0.2s; }
.drop-leave-active { transition: opacity 0.15s; }
.drop-enter-from { transform: translateY(-6px) scale(0.97); opacity: 0; }
.drop-leave-to { opacity: 0; }
:root[data-motion='soft'] .drop-enter-from { transform: none; }
.layout {
  display: flex;
  padding: 3px;
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
.layout button {
  display: grid;
  place-items: center;
  width: 30px;
  height: 28px;
  border-radius: 8px;
  color: var(--text-3);
  transition: color 0.2s, background 0.25s;
}
.layout button.on {
  color: var(--text);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}

.scroller {
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding: 0 var(--gutter-end) 40px var(--gutter);
  scrollbar-width: thin;
  scrollbar-gutter: stable;
}
/* El aire de arriba va como espaciador: con padding-top la fecha fija queda corrida y deja ver las tarjetas por encima. */
.scroller::before {
  content: '';
  display: block;
  height: var(--view-pad-top);
}
.day-h {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0 calc(-1 * var(--gutter-end)) 12px calc(-1 * var(--gutter));
  padding: 16px var(--gutter-end) 8px var(--gutter);
  font-family: var(--font-display);
  font-size: 13px;
  font-weight: 580;
  letter-spacing: 0.01em;
  color: var(--text-2);
  background: var(--bg);
  box-shadow: 0 1px 0 var(--line);
}
.day-h span {
  font-size: var(--t-xs);
  color: var(--text-4);
}
.grid :deep(.card) {
  content-visibility: auto;
  contain-intrinsic-size: auto 220px;
}
.grid {
  isolation: isolate;
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}
.grid.list {
  grid-template-columns: minmax(0, 1fr);
  gap: 6px;
}
.skeletons {
  display: grid;
  gap: 14px;
  padding-top: 20px;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
}
.skeletons :deep(.item) {
  aspect-ratio: 16 / 11;
  border-radius: var(--r-lg);
  padding: 0;
}
.sentinel {
  height: 40px;
  display: grid;
  place-items: center;
}

/* ---------- seleccionar / quitar ---------- */
.selbtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 34px;
  min-width: 38px;
  padding: 0 12px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  color: var(--text-2);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: color 0.2s, background 0.2s, box-shadow 0.2s;
}
.selbtn:hover {
  background: var(--surface-hover);
}
.selbtn.on {
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.bib:not(.desktop) .selbtn {
  width: 38px;
  height: 36px;
  padding: 0;
  background: none;
  box-shadow: none;
  border-radius: 12px;
}
.selbar {
  position: absolute;
  left: 50%;
  bottom: calc(14px + env(safe-area-inset-bottom));
  translate: -50% 0;
  z-index: 12;
  display: flex;
  align-items: center;
  gap: 8px;
  width: max-content;
  max-width: calc(100% - 24px);
  padding: 8px 8px 8px 16px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  box-shadow: var(--shadow-pop), inset 0 0 0 1px var(--line-2);
}
.sel-n {
  font-size: var(--t-md);
  color: var(--text-2);
  white-space: nowrap;
}
.sel-link {
  padding: 0 6px;
  font-size: var(--t-md);
  color: var(--accent);
  white-space: nowrap;
}
.sel-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 36px;
  padding: 0 14px;
  border-radius: var(--r-pill);
  font-size: 13px;
  white-space: nowrap;
  color: var(--text);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.sel-btn.danger {
  color: var(--danger-ink);
  background: var(--danger);
  box-shadow: none;
  font-weight: 600;
}
.sel-btn:disabled {
  opacity: 0.4;
}
.selbar-enter-active { transition: transform 0.5s var(--spring), opacity 0.25s; }
.selbar-leave-active { transition: transform 0.25s var(--ease-out), opacity 0.2s; }
.selbar-enter-from, .selbar-leave-to { opacity: 0; transform: translateY(24px); }
:root[data-motion='soft'] .selbar-enter-from { transform: none; }
@media (max-width: 400px) {
  .selbar { padding-left: 12px; gap: 4px; }
  .sel-btn { padding: 0 11px; }
}

/* ---------- desktop viewer ---------- */
.dim {
  position: absolute;
  inset: 0;
  z-index: 4;
  background: color-mix(in srgb, var(--bg) 55%, transparent);
  backdrop-filter: blur(2px);
}
.side {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  z-index: 5;
  width: min(75%, 1100px);
  display: flex;
  background: var(--bg);
  box-shadow: -24px 0 60px -30px rgba(0, 0, 0, 0.6), -1px 0 0 var(--line);
}
.side > :last-child {
  flex: 1;
  min-width: 0;
}
.resizer {
  position: absolute;
  left: -4px;
  top: 0;
  bottom: 0;
  width: 9px;
  cursor: col-resize;
  z-index: 6;
}
.resizer::after {
  content: '';
  position: absolute;
  left: 4px;
  top: 50%;
  translate: 0 -50%;
  width: 3px;
  height: 44px;
  border-radius: 3px;
  background: var(--line-2);
  transition: background 0.2s, height 0.3s var(--spring);
}
.resizer:hover::after,
.resizer:focus-visible::after,
.side.resizing .resizer::after {
  background: var(--accent);
  height: 72px;
}
.resizing {
  user-select: none;
}
.resizing .side :deep(iframe) {
  pointer-events: none;
}
@media (min-width: 1440px) {
  .dim {
    display: none;
  }
  .side {
    position: relative;
    width: var(--panel);
    flex: none;
  }
  .main {
    transition: none;
  }
}
.panel-enter-active { transition: transform 0.55s var(--spring), opacity 0.3s; }
.panel-leave-active { transition: transform 0.3s var(--ease-out), opacity 0.2s; }
.panel-enter-from, .panel-leave-to { transform: translateX(40px); opacity: 0; }
.dim.panel-enter-from, .dim.panel-leave-to { transform: none; }
:root[data-motion='soft'] .panel-enter-from,
:root[data-motion='soft'] .panel-leave-to { transform: none; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.22s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.quick {
  position: absolute;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  padding: 4vh 6vw;
  background: color-mix(in srgb, var(--bg) 70%, transparent);
  backdrop-filter: blur(10px);
}
.quick-card {
  width: min(1200px, 100%);
  height: 100%;
  border-radius: 18px;
  overflow: hidden;
  box-shadow: var(--shadow-pop);
}
.help {
  width: min(520px, 100%);
  padding: 20px 24px 24px;
  border-radius: 18px;
  background: var(--surface-2);
  box-shadow: var(--shadow-pop);
}
.help h3 {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0 0 14px;
  font-family: var(--font-display);
}
.help dl {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 18px;
  margin: 0;
  font-size: 13px;
}
.help dt {
  color: var(--accent);
  white-space: nowrap;
}
.help dd {
  margin: 0;
  color: var(--text-2);
}

@media (pointer: coarse) {
  .search input,
  select,
  input[type='date'] {
    font-size: 16px;
  }
}

/* ---------- mobile ---------- */
.bib:not(.desktop) .bib-vf :deep(.vf-toolbar) {
  flex-wrap: nowrap;
  gap: 8px;
}
.bib:not(.desktop) .bib-vf :deep(.vh-start) {
  flex: 1;
  min-width: 0;
}
.bib:not(.desktop) .filter-btn,
.bib:not(.desktop) .selbtn {
  flex: none;
}
.bib:not(.desktop) .search.open {
  flex: 1;
  min-width: 0;
}
.bib:not(.desktop) .search:not(.open) {
  min-width: 0;
  flex: none;
  padding: 0;
  background: none;
  box-shadow: none;
}
.s-ic,
.filter-btn {
  display: grid;
  place-items: center;
  width: 38px;
  height: 36px;
  border-radius: 12px;
  color: var(--text-2);
}
.filter-btn.on {
  color: var(--accent);
}
.bib:not(.desktop) .types {
  order: -1;
  flex: 1 1 auto;
  min-width: 0;
  margin-left: calc(-1 * var(--gutter));
  border-radius: 0;
  box-shadow: none;
  background: none;
  padding: 0 0 0 var(--gutter);
  overflow-x: auto;
  gap: 6px;
  scrollbar-width: none;
}
.bib:not(.desktop) .types {
  padding-right: 24px;
  mask-image: linear-gradient(90deg, transparent, #000 var(--gutter), #000 calc(100% - 24px), transparent);
}
.bib:not(.desktop) .type {
  flex: none;
  box-shadow: inset 0 0 0 1px var(--line);
}
.bib:not(.desktop) .type.on {
  box-shadow: none;
}
.bib:not(.desktop) .scroller {
  padding: 0 var(--gutter-end) 24px var(--gutter);
}
.bib:not(.desktop) .scroller::before {
  content: none;
}
.bib:not(.desktop) .day-h {
  margin: 0 calc(-1 * var(--gutter-end)) 10px calc(-1 * var(--gutter));
  padding: 12px var(--gutter-end) 6px var(--gutter);
}
.bib:not(.desktop) .grid:not(.list) {
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
}
@media (min-width: 520px) {
  .bib:not(.desktop) .grid:not(.list) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (min-width: 760px) {
  .bib:not(.desktop) .grid:not(.list) {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
.m-viewer {
  position: fixed;
  inset: 0;
  z-index: 70;
  background: var(--bg);
  touch-action: pan-y;
}
.m-viewer :deep(.bar),
.m-viewer :deep(.volver) {
  touch-action: none;
}
.mview-enter-active { transition: transform 0.5s var(--spring), opacity 0.25s; }
.mview-leave-active { transition: opacity 0.2s; }
.mview-enter-from { transform: translateY(5%) scale(0.97); opacity: 0; }
.mview-leave-to { opacity: 0; }
:root[data-motion='soft'] .mview-enter-from { transform: none; }
.sheet-bg {
  z-index: 75;
}
.sheet {
  width: 100%;
  display: grid;
  gap: 14px;
}
.sheet > *,
.sheet label {
  min-width: 0;
}
.sheet label {
  display: grid;
  gap: 6px;
  font-size: 12px;
  color: var(--text-3);
}
.sheet select,
.sheet input {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 44px;
  font-size: 16px;
  max-width: none;
}
.dates {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.sheet-actions {
  justify-content: flex-end;
}
.sheet-enter-active { transition: opacity 0.25s; }
.sheet-enter-active .sheet { transition: transform 0.5s var(--ease-sheet); }
.sheet-leave-active { transition: opacity 0.2s; }
.sheet-enter-from, .sheet-leave-to { opacity: 0; }
.sheet-enter-from .sheet { transform: translateY(40px); }
:root[data-motion='soft'] .sheet-enter-from .sheet { transform: none; }
</style>
