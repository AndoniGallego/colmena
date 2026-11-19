<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { brandHop, gsap, isSoft, soft, useGsap } from '../../motion'
import { monoGeo } from '../../lib/colmena'
import { MARK_DEFAULTS, beat, breathe, comet, litCount, markMode, type MarkProps } from './marca'

const props = withDefaults(defineProps<MarkProps>(), MARK_DEFAULTS)

const geo = monoGeo()
const lit = computed(() => litCount(props, geo.arc.length))
const mode = computed(() => markMode(props))
const { run } = useGsap()

const svg = ref<SVGSVGElement | null>(null)
const fly = ref<SVGGElement | null>(null)
const bee = ref<SVGPathElement | null>(null)
const wave = ref<SVGPathElement | null>(null)
const cells: SVGGElement[] = []
const glows: SVGGElement[] = []
const lights: SVGPathElement[] = []
const into = <T,>(arr: T[], i: number) => (el: unknown) => {
  if (el) arr[i] = el as T
}

let shown = 0
let spin = 0
let ready = false
let busy = false
let breath: gsap.core.Tween | null = null
let chase: gsap.core.Timeline | null = null
let alert: gsap.core.Timeline | null = null
let hover: gsap.core.Tween | null = null
let turns: gsap.core.Tween | null = null
let dim: gsap.core.Tween | null = null

function stopBreath() {
  breath?.kill()
  breath = null
  gsap.set(glows, { opacity: 1 })
}
function stopChase() {
  if (!chase && !dim) return
  chase?.kill()
  dim?.kill()
  chase = dim = null
  gsap.set(lights, { opacity: 0, scale: 1 })
  gsap.set(svg.value, { opacity: 1 })
  shown = 0
}
function stopAlert() {
  alert?.kill()
  alert = null
  gsap.set(bee.value, { scale: 1 })
  gsap.set(wave.value, { opacity: 0, scale: 1 })
}
function stopMotion() {
  hover?.kill()
  turns?.kill()
  hover = turns = null
  gsap.set(fly.value, { y: 0 })
}

/** La abeja gira de a 60°: el hexágono queda igual, sólo se nota el envión. */
function snap() {
  spin += 60
  return gsap.to(bee.value, { rotation: spin, duration: 0.55, ease: 'back.out(2.6)', overwrite: 'auto' })
}
function scheduleTurns(min: number, max: number) {
  turns = gsap.delayedCall(gsap.utils.random(min, max), () => {
    snap()
    scheduleTurns(min, max)
  })
}

function setLit(n: number, animate: boolean) {
  lights.forEach((el, i) => {
    const on = i < n
    if (!animate) return void gsap.set(el, { opacity: on ? 1 : 0, scale: 1, overwrite: true })
    if (on === i < shown) return
    if (on) gsap.fromTo(el, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.85, ease: 'elastic.out(1.15, 0.42)', delay: Math.max(0, i - shown) * 0.06, overwrite: true })
    else gsap.to(el, { opacity: 0, scale: 0.7, duration: 0.4, ease: 'power2.in', overwrite: true })
  })
  shown = n
}

function apply() {
  if (!ready || busy) return
  run(() => {
    if (mode.value === 'loader') {
      stopBreath()
      stopAlert()
      stopMotion()
      if (isSoft()) {
        chase?.kill()
        chase = null
        gsap.set(lights, { opacity: 0.5, scale: 1 })
        dim ??= gsap.fromTo(svg.value, { opacity: 1 }, { opacity: 0.5, duration: 0.9, ease: 'sine.inOut', yoyo: true, repeat: -1 })
        return
      }
      chase ??= comet(lights, 0.1, 0.5)
      turns ??= gsap.to({}, { duration: 0.45, repeat: -1, onRepeat: snap })
      return
    }
    if (chase || dim) {
      stopChase()
      stopMotion()
    }
    if (isSoft()) {
      stopBreath()
      stopAlert()
      stopMotion()
      setLit(lit.value, false)
      return
    }
    setLit(lit.value, true)
    if (lit.value > 0) breath ??= breathe(glows)
    else stopBreath()
    if (mode.value === 'attention') {
      stopMotion()
      alert ??= beat(bee.value!, wave.value!, 1.2)
      return
    }
    stopAlert()
    const busyBee = mode.value === 'working'
    hover?.kill()
    hover = gsap.to(fly.value, { y: busyBee ? -1.6 : -1.1, duration: busyBee ? 0.9 : 1.8, ease: 'sine.inOut', yoyo: true, repeat: -1 })
    turns?.kill()
    scheduleTurns(busyBee ? 1.6 : 4, busyBee ? 3 : 7.5)
  })
}

function hop() {
  if (!ready || mode.value === 'loader') return
  if (isSoft()) return void run(() => gsap.fromTo(svg.value, { opacity: 0.4 }, { opacity: 1, duration: 0.4 }))
  busy = true
  stopBreath()
  stopMotion()
  run(() => {
    spin += 360
    gsap
      .timeline({
        onComplete: () => {
          busy = false
          apply()
        },
      })
      .to(lights, { opacity: 1, scale: 1, duration: 0.12, stagger: 0.04, overwrite: true }, 0)
      .to(cells, { scale: 1.18, duration: 0.14, yoyo: true, repeat: 1, ease: 'power2.out', stagger: 0.04 }, 0)
      .to(bee.value, { rotation: spin, duration: 0.9, ease: 'power3.inOut' }, 0.2)
      .to(lights, { opacity: (i: number) => (i < shown ? 1 : 0), duration: 0.5, stagger: 0.04 }, 0.5)
  })
}

onMounted(() => {
  run(() => {
    geo.arc.forEach((c, i) => gsap.set([cells[i], lights[i]], { svgOrigin: `${c.x} ${c.y}` }))
    gsap.set([bee.value, wave.value], { svgOrigin: `${geo.bee.x} ${geo.bee.y}` })
    gsap.set(lights, { opacity: 0 })
    const go = () => {
      ready = true
      apply()
    }
    if (!props.intro) return go()
    if (isSoft()) return void gsap.from(svg.value, { opacity: 0, duration: 0.35, onComplete: go })
    gsap
      .timeline({ delay: 0.12, onComplete: go })
      .from(cells, { scale: 0, opacity: 0, duration: 0.7, ease: 'back.out(2)', stagger: 0.05 }, 0)
      .from(fly.value, { x: 18, opacity: 0, duration: 0.9, ease: 'elastic.out(1, 0.5)' }, 0.45)
  })
})

watch([lit, mode, soft], apply)
watch(brandHop, hop)
</script>

<template>
  <svg ref="svg" class="mark" :class="{ off: !live }" :data-mode="mode" viewBox="0 0 64 64" :width="size" :height="size" aria-hidden="true">
    <g v-for="(c, i) in geo.arc" :key="i" :ref="into(cells, i)">
      <path class="ink" :d="c.d" />
      <g :ref="into(glows, i)"><path :ref="into(lights, i)" class="lit" :d="c.d" /></g>
    </g>
    <g ref="fly">
      <path ref="wave" class="wave" :d="geo.bee.d" opacity="0" />
      <path ref="bee" class="bee" :d="geo.bee.d" />
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
.ink { fill: var(--mark-ink); }
.lit { fill: var(--mark-lit); }
.wave { fill: none; stroke: var(--bee); stroke-width: 1.4; }
.bee { fill: var(--bee); transition: fill 0.5s var(--ease-in-out); }
</style>
