<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { gsap, isSoft } from '../motion'

const props = defineProps<{ src: string; alt: string }>()

const box = ref<HTMLElement | null>(null)
const img = ref<HTMLImageElement | null>(null)
const view = { s: 1, x: 0, y: 0 }
const zoomed = ref(false)
const pointers = new Map<number, { x: number; y: number }>()
let pinch = 0
let tween: gsap.core.Tween | null = null

function apply() {
  if (img.value) gsap.set(img.value, { scale: view.s, x: view.x, y: view.y })
  zoomed.value = view.s > 1.02
}

function clamp() {
  const b = box.value
  if (!b) return
  const lim = (b.clientWidth * (view.s - 1)) / 2
  const limY = (b.clientHeight * (view.s - 1)) / 2
  view.x = Math.max(-lim, Math.min(lim, view.x))
  view.y = Math.max(-limY, Math.min(limY, view.y))
}

function zoomAt(next: number, cx: number, cy: number) {
  const b = box.value
  if (!b) return
  const s = Math.max(1, Math.min(8, next))
  const r = b.getBoundingClientRect()
  const px = cx - (r.left + r.width / 2)
  const py = cy - (r.top + r.height / 2)
  view.x = px - ((px - view.x) / view.s) * s
  view.y = py - ((py - view.y) / view.s) * s
  view.s = s
  if (s === 1) view.x = view.y = 0
  clamp()
  apply()
}

function onWheel(e: WheelEvent) {
  e.preventDefault()
  tween?.kill()
  zoomAt(view.s * Math.exp(-e.deltaY * 0.0022), e.clientX, e.clientY)
}

function onDown(e: PointerEvent) {
  pointers.set(e.pointerId, { x: e.clientX, y: e.clientY })
  box.value?.setPointerCapture(e.pointerId)
  if (pointers.size === 2) pinch = dist()
}
function dist() {
  const [a, b] = [...pointers.values()]
  return Math.hypot(a.x - b.x, a.y - b.y)
}
function onMove(e: PointerEvent) {
  const p = pointers.get(e.pointerId)
  if (!p) return
  const dx = e.clientX - p.x
  const dy = e.clientY - p.y
  p.x = e.clientX
  p.y = e.clientY
  if (pointers.size === 2) {
    const d = dist()
    const [a, b] = [...pointers.values()]
    if (pinch) zoomAt(view.s * (d / pinch), (a.x + b.x) / 2, (a.y + b.y) / 2)
    pinch = d
  } else if (view.s > 1) {
    view.x += dx
    view.y += dy
    clamp()
    apply()
  }
}
function onUp(e: PointerEvent) {
  pointers.delete(e.pointerId)
  pinch = 0
}

/** Double click toggles between fitting the box and the image at its real size. */
function toggle(e: MouseEvent) {
  const el = img.value
  const b = box.value
  if (!el || !b) return
  tween?.kill()
  const real = Math.max(1, el.naturalWidth / Math.max(1, el.clientWidth))
  const target = view.s > 1.02 ? 1 : Math.min(8, real > 1.05 ? real : 2.5)
  const from = { s: view.s, x: view.x, y: view.y }
  const r = b.getBoundingClientRect()
  const px = e.clientX - (r.left + r.width / 2)
  const py = e.clientY - (r.top + r.height / 2)
  const end = { s: target, x: target === 1 ? 0 : px - ((px - from.x) / from.s) * target, y: target === 1 ? 0 : py - ((py - from.y) / from.s) * target }
  const run = { t: 0 }
  tween = gsap.to(run, {
    t: 1,
    duration: isSoft() ? 0.01 : 0.45,
    ease: 'power3.out',
    onUpdate: () => {
      view.s = from.s + (end.s - from.s) * run.t
      view.x = from.x + (end.x - from.x) * run.t
      view.y = from.y + (end.y - from.y) * run.t
      clamp()
      apply()
    },
  })
}

watch(
  () => props.src,
  () => {
    tween?.kill()
    Object.assign(view, { s: 1, x: 0, y: 0 })
    apply()
  },
)
onBeforeUnmount(() => tween?.kill())
</script>

<template>
  <div
    ref="box"
    class="zoom"
    :class="{ zoomed }"
    @wheel.prevent="onWheel"
    @pointerdown="onDown"
    @pointermove="onMove"
    @pointerup="onUp"
    @pointercancel="onUp"
    @lostpointercapture="onUp"
    @dblclick="toggle"
  >
    <img ref="img" :src="src" :alt="alt" draggable="false" />
  </div>
</template>

<style scoped>
.zoom {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  overflow: hidden;
  touch-action: none;
  cursor: zoom-in;
  background:
    repeating-conic-gradient(color-mix(in srgb, var(--text) 5%, transparent) 0% 25%, transparent 0% 50%) 0 0 / 20px 20px;
}
.zoom.zoomed {
  cursor: grab;
}
.zoom.zoomed:active {
  cursor: grabbing;
}
img {
  max-width: 100%;
  max-height: 100%;
  object-fit: contain;
  user-select: none;
  will-change: transform;
  outline: 1px solid var(--img-outline);
  outline-offset: -1px;
}
</style>
