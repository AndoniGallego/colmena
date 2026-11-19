<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { brandHop, gsap, isSoft, soft, useGsap } from '../../motion'
import { panalGeo } from '../../lib/colmena'
import { celdasQueTerminan, type EstadoCelda } from '../../lib/notchCeldas'
import { MARK_DEFAULTS, beat, breathe, comet, litCount, markMode, type MarkProps } from './marca'

const props = withDefaults(defineProps<MarkProps>(), MARK_DEFAULTS)

const geo = panalGeo()
const lit = computed(() => litCount(props, 6))
const mode = computed(() => markMode(props))
const hasCells = computed(() => props.cells !== undefined)
const ringCells = computed(() =>
  props.cells === undefined ? [] : Array.from({ length: 6 }, (_, i) => props.cells![i] ?? 'vacia'),
)
const { run } = useGsap()

const svg = ref<SVGSVGElement | null>(null)
const core = ref<SVGPathElement | null>(null)
const wave = ref<SVGPathElement | null>(null)
const cells: SVGGElement[] = []
const glows: SVGGElement[] = []
const lights: SVGPathElement[] = []
const into = <T,>(arr: T[], i: number) => (el: unknown) => {
  if (el) arr[i] = el as T
}

let shown = 0
let ready = false
let busy = false
let breath: gsap.core.Tween | null = null
let chase: gsap.core.Timeline | null = null
let alert: gsap.core.Timeline | null = null
let firefly: gsap.core.Tween | null = null
let hum: gsap.core.Tween | null = null
let dim: gsap.core.Tween | null = null
const cellLoops: (gsap.core.Timeline | gsap.core.Tween | null)[] = Array.from({ length: 6 }, () => null)
let waveLoop: gsap.core.Timeline | null = null
let prevRing: EstadoCelda[] | null = null

function stopCellLoops() {
  cellLoops.forEach((l) => l?.kill())
  cellLoops.fill(null)
  waveLoop?.kill()
  waveLoop = null
}

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
  gsap.set(core.value, { scale: 1 })
  gsap.set(wave.value, { opacity: 0, scale: 1 })
}
function stopFirefly() {
  firefly?.kill()
  firefly = null
}
function stopHum() {
  hum?.kill()
  hum = null
  gsap.set(core.value, { scale: 1 })
}

/** Enciende las primeras `n` celdas del anillo; las nuevas brotan con rebote. */
function setLit(n: number, animate: boolean) {
  lights.forEach((el, i) => {
    const on = i < n
    if (!animate) return void gsap.set(el, { opacity: on ? 1 : 0, scale: 1, overwrite: true })
    if (on === i < shown) return
    if (on) gsap.fromTo(el, { opacity: 0, scale: 0.4 }, { opacity: 1, scale: 1, duration: 0.9, ease: 'elastic.out(1.15, 0.42)', delay: Math.max(0, i - shown) * 0.08, overwrite: true })
    else gsap.to(el, { opacity: 0, scale: 0.7, duration: 0.45, ease: 'power2.in', overwrite: true })
  })
  shown = n
}

/** En reposo, una celda al azar se prende apenas y se apaga: la colmena sigue viva. */
function scheduleFirefly(delay: number) {
  firefly = gsap.delayedCall(delay, () => {
    const el = gsap.utils.random(lights)
    gsap.fromTo(el, { opacity: 0 }, { opacity: 0.42, duration: 1.1, ease: 'sine.inOut', yoyo: true, repeat: 1, overwrite: true })
    scheduleFirefly(gsap.utils.random(2.2, 4.4))
  })
}

function cellBeat(el: Element) {
  return gsap
    .timeline({ repeat: -1, repeatDelay: 0.55 })
    .fromTo(el, { scale: 1 }, { scale: 1.24, duration: 0.17, ease: 'power2.out' })
    .to(el, { scale: 1, duration: 0.75, ease: 'elastic.out(1.1, 0.4)' })
}

function amberWave() {
  return gsap
    .timeline({ repeat: -1, repeatDelay: 0.55 })
    .fromTo(wave.value, { scale: 0.7, opacity: 0.75 }, { scale: 1.9, opacity: 0, duration: 1.15, ease: 'power2.out' })
}

function applyCells() {
  const ring = ringCells.value
  stopBreath()
  stopChase()
  stopAlert()
  stopFirefly()
  stopHum()
  stopCellLoops()
  gsap.set(core.value, { scale: 1 })

  const flashes = prevRing ? celdasQueTerminan(prevRing, ring) : []

  if (isSoft()) {
    ring.forEach((st, i) => {
      gsap.set(lights[i], { opacity: st === 'vacia' ? 0 : 1, scale: 1 })
      gsap.set(glows[i], { opacity: 1 })
      gsap.set(cells[i], { scale: 1 })
    })
    gsap.set(wave.value, { opacity: 0, scale: 1 })
    prevRing = [...ring]
    return
  }

  ring.forEach((st, i) => {
    gsap.set(lights[i], { opacity: st === 'vacia' ? 0 : 1, scale: 1 })
    gsap.set(cells[i], { scale: 1 })
    if (st === 'te-toca') cellLoops[i] = cellBeat(lights[i]!)
    else if (st === 'trabajando') {
      cellLoops[i] = gsap.to(lights[i], {
        opacity: 0.45,
        duration: 1.4,
        ease: 'sine.inOut',
        yoyo: true,
        repeat: -1,
        delay: (i % 6) * 0.28,
      })
    } else if (st === 'termino' && flashes.includes(i)) {
      cellLoops[i] = gsap.fromTo(lights[i], { scale: 1.45 }, { scale: 1, duration: 1, ease: 'elastic.out(1, 0.45)' })
    }
  })

  if (ring.some((st) => st === 'te-toca')) waveLoop = amberWave()
  else gsap.set(wave.value, { opacity: 0, scale: 1 })

  prevRing = [...ring]
}

function apply() {
  if (!ready || busy) return
  run(() => {
    if (hasCells.value) return applyCells()
    if (mode.value === 'loader') {
      stopBreath()
      stopAlert()
      stopFirefly()
      if (isSoft()) {
        chase?.kill()
        chase = null
        gsap.set(lights, { opacity: 0.55, scale: 1 })
        dim ??= gsap.fromTo(svg.value, { opacity: 1 }, { opacity: 0.5, duration: 0.9, ease: 'sine.inOut', yoyo: true, repeat: -1 })
        return
      }
      dim?.kill()
      dim = null
      gsap.set(svg.value, { opacity: 1 })
      chase ??= comet(lights, 0.15, 0.62)
      hum ??= gsap.to(core.value, { scale: 0.9, duration: 0.45, ease: 'sine.inOut', yoyo: true, repeat: -1 })
      return
    }
    if (chase || dim) {
      stopChase()
      stopHum()
    }
    if (isSoft()) {
      stopBreath()
      stopAlert()
      stopFirefly()
      stopHum()
      setLit(lit.value, false)
      return
    }
    setLit(lit.value, true)
    if (lit.value > 0) {
      stopFirefly()
      breath ??= breathe(glows)
    } else {
      stopBreath()
      if (!firefly) scheduleFirefly(gsap.utils.random(0.8, 2))
    }
    if (mode.value === 'attention') {
      stopHum()
      alert ??= beat(core.value!, wave.value!)
    } else {
      stopAlert()
      hum ??= gsap.to(core.value, { scale: 1.045, duration: 2.4, ease: 'sine.inOut', yoyo: true, repeat: -1 })
    }
  })
}

/** Al confirmar un traspaso, una ola recorre el anillo. */
function hop() {
  if (!ready || mode.value === 'loader') return
  if (isSoft()) return void run(() => gsap.fromTo(svg.value, { opacity: 0.4 }, { opacity: 1, duration: 0.4 }))
  busy = true
  stopBreath()
  stopFirefly()
  run(() => {
    gsap
      .timeline({
        onComplete: () => {
          busy = false
          apply()
        },
      })
      .to(lights, { opacity: 1, scale: 1, duration: 0.14, ease: 'power2.out', stagger: 0.06, overwrite: true }, 0)
      .to(cells, { scale: 1.16, duration: 0.16, ease: 'power2.out', yoyo: true, repeat: 1, stagger: 0.06 }, 0)
      .to(core.value, { scale: 0.86, duration: 0.14, yoyo: true, repeat: 1, ease: 'power2.inOut' }, 0)
      .to(lights, { opacity: (i: number) => (i < shown ? 1 : 0), duration: 0.55, ease: 'power2.inOut', stagger: 0.06 }, 0.42)
  })
}

onMounted(() => {
  run(() => {
    geo.ring.forEach((c, i) => gsap.set([cells[i], lights[i]], { svgOrigin: `${c.x} ${c.y}` }))
    gsap.set([core.value, wave.value], { svgOrigin: '32 32' })
    gsap.set(lights, { opacity: 0 })
    const go = () => {
      ready = true
      apply()
    }
    if (!props.intro) return go()
    if (isSoft()) return void gsap.from(svg.value, { opacity: 0, duration: 0.35, onComplete: go })
    gsap
      .timeline({ delay: 0.12, onComplete: go })
      .from(core.value, { scale: 0, duration: 0.7, ease: 'back.out(2.2)' }, 0)
      .from(cells, { scale: 0, opacity: 0, duration: 0.85, ease: 'elastic.out(1, 0.5)', stagger: 0.07 }, 0.18)
  })
})

watch([lit, mode, soft], apply)
watch(
  () => (props.cells ? [...props.cells] : undefined),
  () => apply(),
)
watch(brandHop, hop)
</script>

<template>
  <svg
    ref="svg"
    class="mark"
    :class="{ off: !live }"
    :data-mode="mode"
    :data-cells="hasCells ? '' : undefined"
    viewBox="0 0 64 64"
    :width="size"
    :height="size"
    aria-hidden="true"
  >
    <g v-for="(c, i) in geo.ring" :key="i" :ref="into(cells, i)" :data-cell="hasCells ? ringCells[i] : undefined">
      <path class="dim" :d="c.d" />
      <g :ref="into(glows, i)"><path :ref="into(lights, i)" class="lit" :d="c.d" /></g>
    </g>
    <path ref="wave" class="wave" :d="geo.center.d" opacity="0" />
    <path ref="core" class="core" :d="geo.center.d" />
  </svg>
</template>

<style scoped>
.mark {
  display: block;
  flex: none;
  overflow: visible;
}
.dim { fill: var(--mark-dim); }
.lit { fill: var(--mark-lit); }
.core {
  fill: var(--mark-ink);
  transition: fill 0.5s var(--ease-in-out);
}
.wave { fill: none; stroke: var(--mark-alert); stroke-width: 1.6; }
.mark[data-mode='attention'] .core { fill: var(--mark-alert); }
.mark[data-cells] .lit { opacity: 1; }
.mark[data-cells] [data-cell='te-toca'] .lit { fill: var(--st-blocked); }
.mark[data-cells] [data-cell='trabajando'] .lit { fill: var(--st-working); }
.mark[data-cells] [data-cell='termino'] .lit { fill: var(--st-done); }
.mark[data-cells] [data-cell='tranquila'] .lit { fill: var(--mark-dim); }
.mark[data-cells] [data-cell='vacia'] .lit { opacity: 0; }
.mark[data-cells] [data-cell='vacia'] .dim { opacity: 0.45; }
.mark[data-cells] .core {
  fill: var(--accent);
  filter: drop-shadow(0 0 2.5px color-mix(in srgb, var(--accent) 55%, transparent));
}
</style>
