<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import type { TranscriptFoto } from '../api/types'
import { stepIndex } from '../lib/chatFotos'
import { actVerEnBiblioteca } from '../lib/fotoCarruselLibrary'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { cachedLibItem, fresh, openInLibrary } from '../state/biblioteca'
import BibImage from './BibImage.vue'
import Icon from './Icon.vue'

const props = defineProps<{ fotos: TranscriptFoto[]; start: number; from?: HTMLElement | null }>()
const emit = defineEmits<{ close: [] }>()

const index = ref(Math.min(Math.max(props.start, 0), Math.max(0, props.fotos.length - 1)))
const src = ref('')
const title = ref('')
const sheet = ref<HTMLElement | null>(null)
const { onKeydown: trapKeydown } = useFocusTrap(sheet, () => true, { onEscape: () => emit('close') })
const { run } = useGsap()

const total = computed(() => props.fotos.length)
const counter = computed(() => (total.value ? `${index.value + 1} / ${total.value}` : ''))

async function loadAt(i: number) {
  const id = props.fotos[i]?.id
  if (!id) return
  const item = await cachedLibItem(id)
  if (!item) {
    src.value = ''
    title.value = 'Captura'
    return
  }
  const ready = await fresh(item)
  src.value = ready.src
  title.value = ready.title || 'Captura'
}

watch(index, (i) => loadAt(i), { immediate: true })

function go(delta: number) {
  const next = stepIndex(index.value, delta, total.value)
  if (next !== index.value) {
    haptic(4)
    index.value = next
  }
}

function onWindowKey(e: KeyboardEvent) {
  if (e.key === 'Escape' || e.defaultPrevented) return
  const t = e.target instanceof Element ? e.target : null
  if (t?.closest('input, textarea, select, [contenteditable="true"]')) return
  const modal = t?.closest('[aria-modal="true"]')
  if (modal && !modal.classList.contains('fc-root')) return
  if (e.key === 'ArrowLeft') go(-1)
  if (e.key === 'ArrowRight') go(1)
}

function onRootKeydown(e: KeyboardEvent) {
  trapKeydown(e)
}

const SWIPE_X = 60
const SWIPE_V = 0.5
const CLOSE_Y = 90
const LOCK = 8
const STALE_MS = 80

const pic = ref<HTMLElement | null>(null)
const pointers = new Set<number>()
let g: { x: number; y: number; lx: number; lt: number; vx: number; axis: '' | 'x' | 'y'; dead: boolean; onImage: boolean } | null = null
let gx = 0
let gy = 0

function rubber(d: number) {
  return Math.sign(d) * Math.sqrt(Math.abs(d)) * 3
}
function atEdge(dx: number) {
  return (dx > 0 && index.value === 0) || (dx < 0 && index.value === total.value - 1)
}
function isZoomed() {
  return !!sheet.value?.querySelector('.zoom.zoomed')
}

function settle() {
  const el = pic.value
  if (!el) return
  gsap.killTweensOf(el)
  gsap.set(el, { x: gx, y: gy })
  if (isSoft()) gsap.set(el, { x: 0, y: 0, clearProps: 'transform' })
  else gsap.to(el, { x: 0, y: 0, duration: 0.25, ease: 'power3.out', clearProps: 'transform' })
}

function onPointerDown(e: PointerEvent) {
  if (e.pointerType === 'mouse' || (e.target as Element | null)?.closest('button, a')) return
  pointers.add(e.pointerId)
  if (pointers.size > 1) {
    if (g && !g.dead) {
      g.dead = true
      gx = gy = 0
      if (pic.value) pic.value.style.transform = ''
    }
    return
  }
  gsap.killTweensOf(pic.value)
  const onImage = !!(e.target as Element | null)?.closest('.zoom')
  g = { x: e.clientX, y: e.clientY, lx: e.clientX, lt: e.timeStamp, vx: 0, axis: '', dead: isZoomed(), onImage }
  gx = gy = 0
}

function onPointerMove(e: PointerEvent) {
  if (!g || g.dead || !pointers.has(e.pointerId)) return
  const dx = e.clientX - g.x
  const dy = e.clientY - g.y
  if (!g.axis) {
    if (Math.max(Math.abs(dx), Math.abs(dy)) < LOCK) return
    g.axis = Math.abs(dx) >= Math.abs(dy) ? 'x' : 'y'
    try {
      if (!g.onImage) sheet.value?.setPointerCapture?.(e.pointerId)
    } catch {
      /* captura no disponible */
    }
  }
  const dt = e.timeStamp - g.lt
  if (dt > 0) g.vx = (e.clientX - g.lx) / dt
  g.lx = e.clientX
  g.lt = e.timeStamp
  if (g.axis === 'x') {
    gx = atEdge(dx) ? rubber(dx) : dx
    gy = 0
  } else {
    gy = dy > 0 ? dy : rubber(dy)
    gx = 0
  }
  if (pic.value) pic.value.style.transform = `translate(${gx}px, ${gy}px)`
}

function onPointerEnd(e: PointerEvent) {
  pointers.delete(e.pointerId)
  const cur = g
  if (pointers.size > 0 || !cur) return
  g = null
  if (cur.dead) return
  const dx = e.clientX - cur.x
  const dy = e.clientY - cur.y
  const cancelled = e.type === 'pointercancel'
  if (e.timeStamp - cur.lt > STALE_MS) cur.vx = 0
  if (!cancelled && cur.axis === 'y' && dy > CLOSE_Y) {
    emit('close')
    return
  }
  if (!cancelled && cur.axis === 'x' && (Math.abs(dx) > SWIPE_X || Math.abs(cur.vx) > SWIPE_V)) {
    go(dx < 0 ? 1 : -1)
    gx = atEdge(dx) ? gx : 0
  }
  settle()
}

function openLibrary() {
  actVerEnBiblioteca(props.fotos[index.value]?.id, openInLibrary, () => emit('close'))
}

function enter() {
  const el = sheet.value
  const from = props.from
  if (!el) return
  if (isSoft() || !from) {
    run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2 }))
    return
  }
  const a = from.getBoundingClientRect()
  const b = el.getBoundingClientRect()
  const sx = a.width / Math.max(b.width, 1)
  const sy = a.height / Math.max(b.height, 1)
  const tx = a.left + a.width / 2 - (b.left + b.width / 2)
  const ty = a.top + a.height / 2 - (b.top + b.height / 2)
  run(() =>
    gsap.fromTo(el, { x: tx, y: ty, scaleX: sx, scaleY: sy, transformOrigin: 'center center', borderRadius: 12 },
      { x: 0, y: 0, scaleX: 1, scaleY: 1, borderRadius: 0, duration: 0.45, ease: 'power3.out', clearProps: 'transform,borderRadius' }),
  )
}

function leave(_el: Element, done: () => void) {
  const el = sheet.value
  const from = props.from
  if (!el || isSoft() || !from) {
    done()
    return
  }
  const a = from.getBoundingClientRect()
  const b = el.getBoundingClientRect()
  const sx = a.width / Math.max(b.width, 1)
  const sy = a.height / Math.max(b.height, 1)
  const tx = a.left + a.width / 2 - (b.left + b.width / 2)
  const ty = a.top + a.height / 2 - (b.top + b.height / 2)
  run(() =>
    gsap.to(el, {
      x: tx, y: ty, scaleX: sx, scaleY: sy, borderRadius: 12, duration: 0.35, ease: 'power2.in',
      onComplete: done,
    }),
  )
}

onMounted(() => {
  window.addEventListener('keydown', onWindowKey)
  enter()
})
onBeforeUnmount(() => window.removeEventListener('keydown', onWindowKey))
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @leave="leave">
      <div class="fc-root" role="dialog" aria-modal="true" :aria-label="title" @click.self="emit('close')" @keydown="onRootKeydown">
        <div ref="sheet" class="fc-sheet" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerEnd" @pointercancel="onPointerEnd">
          <header class="fc-bar">
            <button type="button" class="fc-icon" aria-label="Cerrar" @click="emit('close')"><Icon name="close" :size="20" /></button>
            <span class="fc-count mono">{{ counter }}</span>
            <button type="button" class="fc-lib" @click="openLibrary">Ver en Biblioteca</button>
          </header>
          <div class="fc-stage">
            <div class="fc-slot fc-start">
              <button v-if="total > 1" type="button" class="fc-nav prev" aria-label="Anterior" @click="go(-1)"><Icon name="back" :size="22" /></button>
            </div>
            <div ref="pic" class="fc-pic">
              <BibImage v-if="src" :src="src" :alt="title" />
              <p v-else class="fc-miss">No pude cargar la captura</p>
            </div>
            <div class="fc-slot fc-end">
              <button v-if="total > 1" type="button" class="fc-nav next" aria-label="Siguiente" @click="go(1)"><Icon name="next" :size="22" /></button>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.fc-root {
  position: fixed;
  inset: 0;
  z-index: 90;
  background: color-mix(in srgb, var(--bg) 12%, #000 88%);
  display: flex;
  align-items: stretch;
  justify-content: center;
}
.fc-sheet {
  touch-action: none;
  width: 100%;
  max-width: 1200px;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.fc-bar {
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 0.85rem;
  color: var(--text);
}
.fc-icon {
  border: 0;
  background: transparent;
  color: inherit;
  padding: 0.35rem;
  border-radius: 8px;
}
.fc-count {
  flex: 1;
  text-align: center;
  opacity: 0.85;
  font-size: 0.85rem;
}
.fc-lib {
  border: 1px solid var(--line);
  background: var(--surface);
  color: var(--text);
  border-radius: var(--r-pill);
  padding: 0.35rem 0.75rem;
  font-size: 0.82rem;
}
.fc-stage {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  padding: 0 0.25rem 1rem;
}
.fc-slot {
  display: flex;
  align-items: center;
  justify-content: center;
  min-width: 0;
}
.fc-start {
  grid-column: 1;
}
.fc-end {
  grid-column: 3;
}
.fc-pic {
  grid-column: 2;
  position: relative;
  min-width: 0;
  min-height: min(60vh, 520px);
}
.fc-nav {
  border: 0;
  background: color-mix(in srgb, var(--surface) 70%, transparent);
  color: var(--text);
  border-radius: var(--r-pill);
  width: 2.5rem;
  height: 2.5rem;
  display: grid;
  place-items: center;
}
.fc-pic :deep(.zoom) {
  max-height: min(78vh, 900px);
}
.fc-miss {
  text-align: center;
  opacity: 0.7;
  padding: 2rem;
}
@media (max-width: 640px) {
  .fc-nav.prev, .fc-nav.next { display: none; }
}
</style>
