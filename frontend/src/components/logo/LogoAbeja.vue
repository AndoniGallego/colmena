<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { brandHop, gsap, isSoft, soft, useGsap } from '../../motion'
import { ABEJA, abejaGeo } from '../../lib/colmena'
import { MARK_DEFAULTS, beat, litCount, markMode, type MarkProps } from './marca'

const props = withDefaults(defineProps<MarkProps>(), MARK_DEFAULTS)

const geo = abejaGeo()
const lit = computed(() => litCount(props, 6))
const mode = computed(() => markMode(props))
const { run } = useGsap()

const svg = ref<SVGSVGElement | null>(null)
const ringEl = ref<SVGPathElement | null>(null)
const coreEl = ref<SVGPathElement | null>(null)
const track = ref<SVGPathElement | null>(null)
const trail = ref<SVGPathElement | null>(null)
const fly = ref<SVGGElement | null>(null)
const bee = ref<SVGCircleElement | null>(null)
const halo = ref<SVGCircleElement | null>(null)
const wave = ref<SVGCircleElement | null>(null)

const TAIL = 0.2
const pos = { p: 0 }
let len = 0
let ready = false
let busy = false
let loop: gsap.core.Tween | null = null
let alert: gsap.core.Timeline | null = null
let glow: gsap.core.Tween | null = null
let dim: gsap.core.Tween | null = null

/** Ubica la abeja en la fracción `p` de la vuelta y dibuja la estela detrás. */
function place() {
  const t = ((pos.p % 1) + 1) % 1
  const pt = track.value!.getPointAtLength(t * len)
  gsap.set(fly.value, { x: pt.x - geo.bee.x, y: pt.y - geo.bee.y })
  gsap.set(trail.value, { drawSVG: `${((t + 1 - TAIL) / 2) * 100}% ${((t + 1) / 2) * 100}%` })
}

const speed = () => (mode.value === 'loader' ? 2.2 : 1 + Math.min(0.6, Math.max(0, lit.value - 1) * 0.12))

function startLoop() {
  if (loop) return void gsap.to(loop, { timeScale: speed(), duration: 0.8 })
  loop = gsap.to(pos, { p: '+=1', duration: 4.2, ease: 'none', repeat: -1, onUpdate: place })
  loop.timeScale(0)
  gsap.to(loop, { timeScale: speed(), duration: 1.1, ease: 'power1.in' })
  gsap.to(trail.value, { opacity: 1, duration: 0.6 })
}

/** Lleva la abeja hacia adelante hasta su vértice de casa y apaga la estela. */
function park(onDone?: () => void) {
  loop?.kill()
  loop = null
  const target = Math.ceil(pos.p + 0.02)
  const d = Math.max(0.6, (target - pos.p) * 2.4)
  gsap.to(trail.value, { opacity: 0, duration: 0.45, delay: Math.max(0, d - 0.45) })
  gsap.to(pos, {
    p: target,
    duration: d,
    ease: 'power2.out',
    onUpdate: place,
    onComplete: () => {
      pos.p = 0
      place()
      onDone?.()
    },
  })
}

function stopAlert() {
  alert?.kill()
  alert = null
  gsap.set(bee.value, { scale: 1 })
  gsap.set(wave.value, { opacity: 0, scale: 1 })
}
function stopGlow() {
  glow?.kill()
  glow = null
  gsap.set(halo.value, { opacity: 0, scale: 1 })
}

function apply() {
  if (!ready || busy) return
  run(() => {
    if (isSoft()) {
      loop?.kill()
      loop = null
      gsap.killTweensOf(pos)
      pos.p = 0
      place()
      gsap.set(trail.value, { opacity: 0 })
      stopAlert()
      stopGlow()
      if (mode.value === 'loader') dim ??= gsap.fromTo(svg.value, { opacity: 1 }, { opacity: 0.5, duration: 0.9, ease: 'sine.inOut', yoyo: true, repeat: -1 })
      else {
        dim?.kill()
        dim = null
        gsap.set(svg.value, { opacity: 1 })
      }
      return
    }
    dim?.kill()
    dim = null
    gsap.set(svg.value, { opacity: 1 })
    if (mode.value === 'working' || mode.value === 'loader') {
      stopAlert()
      stopGlow()
      startLoop()
    } else if (mode.value === 'attention') {
      stopGlow()
      if (loop) park(() => mode.value === 'attention' && !busy && (alert ??= beat(bee.value!, wave.value!, 1.24)))
      else alert ??= beat(bee.value!, wave.value!, 1.24)
    } else {
      stopAlert()
      if (loop) park()
      glow ??= gsap.fromTo(halo.value, { opacity: 0, scale: 0.9 }, { opacity: 0.35, scale: 1.55, duration: 2.2, ease: 'sine.inOut', yoyo: true, repeat: -1 })
    }
  })
}

/** Al confirmar un traspaso, la abeja da una vuelta rápida. */
function hop() {
  if (!ready || mode.value === 'loader') return
  if (isSoft()) return void run(() => gsap.fromTo(bee.value, { opacity: 0.2 }, { opacity: 1, duration: 0.4 }))
  busy = true
  loop?.kill()
  loop = null
  stopAlert()
  run(() => {
    const from = pos.p
    gsap
      .timeline({
        onComplete: () => {
          pos.p = 0
          place()
          busy = false
          apply()
        },
      })
      .to(trail.value, { opacity: 1, duration: 0.15 }, 0)
      .to(pos, { p: Math.ceil(from + 0.02) + 1, duration: 1.15, ease: 'power3.inOut', onUpdate: place }, 0)
      .to(ringEl.value, { scale: 1.05, duration: 0.14, yoyo: true, repeat: 1, ease: 'power2.out' }, 1.0)
      .to(trail.value, { opacity: 0, duration: 0.35 }, 1.0)
  })
}

onMounted(() => {
  len = track.value!.getTotalLength()
  run(() => {
    gsap.set([ringEl.value, coreEl.value], { svgOrigin: '32 32' })
    gsap.set([bee.value, halo.value, wave.value], { svgOrigin: `${geo.bee.x} ${geo.bee.y}` })
    place()
    const go = () => {
      ready = true
      apply()
    }
    if (!props.intro) return go()
    if (isSoft()) return void gsap.from(svg.value, { opacity: 0, duration: 0.35, onComplete: go })
    gsap
      .timeline({ delay: 0.12, onComplete: go })
      .fromTo(ringEl.value, { drawSVG: '0%', rotation: -60 }, { drawSVG: '100%', rotation: 0, duration: 1.0, ease: 'power3.inOut' }, 0)
      .from(coreEl.value, { scale: 0, duration: 0.6, ease: 'back.out(2.4)' }, 0.55)
      .from(fly.value, { y: -26, opacity: 0, duration: 0.9, ease: 'elastic.out(1, 0.42)' }, 0.7)
  })
})

watch([lit, mode, soft], apply)
watch(brandHop, hop)
</script>

<template>
  <svg ref="svg" class="mark" :class="{ off: !live }" :data-mode="mode" viewBox="0 0 64 64" :width="size" :height="size" aria-hidden="true">
    <path ref="track" :d="geo.track" fill="none" stroke="none" />
    <path ref="ringEl" class="ring" :d="geo.ring" :stroke-width="ABEJA.stroke" />
    <path ref="coreEl" class="core" :d="geo.core" />
    <path ref="trail" class="trail" :d="geo.trail" opacity="0" />
    <g ref="fly">
      <circle ref="halo" class="halo" :cx="geo.bee.x" :cy="geo.bee.y" :r="ABEJA.bee" opacity="0" />
      <circle ref="wave" class="wave" :cx="geo.bee.x" :cy="geo.bee.y" :r="ABEJA.bee" opacity="0" />
      <circle ref="bee" class="bee" :cx="geo.bee.x" :cy="geo.bee.y" :r="ABEJA.bee" />
    </g>
  </svg>
</template>

<style scoped>
.mark {
  display: block;
  flex: none;
  overflow: visible;
  --bee: var(--mark-lit);
}
.mark[data-mode='attention'] { --bee: var(--mark-alert); }
.ring { fill: none; stroke: var(--mark-ink); stroke-linejoin: round; }
.core { fill: var(--mark-ink); }
.trail { fill: none; stroke: var(--mark-lit); stroke-width: 3.4; stroke-linecap: round; stroke-linejoin: round; }
.halo { fill: var(--bee); }
.wave { fill: none; stroke: var(--bee); stroke-width: 2; }
.bee {
  fill: var(--bee);
  stroke: var(--mark-cut, var(--bg));
  stroke-width: 3.2;
  paint-order: stroke;
  transition: fill 0.5s var(--ease-in-out);
}
</style>
