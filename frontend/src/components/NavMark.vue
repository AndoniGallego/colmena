<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { finePointer, gsap, isSoft, soft, useGsap } from '../motion'

const props = withDefaults(defineProps<{ name: 'board' | 'clock' | 'library' | 'merge'; size?: number; active?: boolean }>(), { size: 18 })

const { run } = useGsap()
const a = ref<SVGElement | null>(null)
const b = ref<SVGElement | null>(null)
const c = ref<SVGElement | null>(null)

let idle: gsap.core.Tween | null = null
let tick: gsap.core.Tween | null = null
let minute = 0
let hour = 125

const d = ref<SVGElement | null>(null)
const root = ref<SVGSVGElement | null>(null)
let current: gsap.core.Timeline | gsap.core.Tween | null = null

const pick = <T,>(list: T[]) => list[Math.floor(Math.random() * list.length)]

function branchLen() {
  return (b.value as SVGPathElement | null)?.getTotalLength?.() || 16
}

// Un commit sale del tronco, recorre la rama y se funde en el nodo de destino, que lo recibe con rebote.
function mergeCommit(big = false) {
  return gsap
    .timeline()
    .set(d.value, { opacity: 0, scale: 0.4, transformOrigin: '50% 50%' })
    .to(a.value, { scale: big ? 1.4 : 1.25, duration: 0.14, ease: 'power2.out', yoyo: true, repeat: 1 }, 0)
    .to(d.value, { opacity: 1, scale: 1, duration: 0.14, ease: 'power2.out' }, 0.1)
    .to(d.value, { motionPath: { path: b.value as SVGPathElement, start: 0.06, end: 0.92 }, duration: big ? 0.6 : 0.7, ease: 'power1.inOut' }, 0.1)
    .to(d.value, { scale: 0, opacity: 0, duration: 0.12, ease: 'power2.in' }, '-=0.08')
    .fromTo(c.value, { scale: 0.7 }, { scale: 1, duration: big ? 0.9 : 0.75, ease: 'elastic.out(1.3, 0.35)' }, '<')
}

// La rama se despega del tronco y se vuelve a dibujar; los nodos laten al reconectarse.
function mergeRedraw() {
  const path = b.value
  const len = branchLen()
  return gsap
    .timeline()
    .set(path, { strokeDasharray: len, strokeDashoffset: 0 })
    .to(path, { strokeDashoffset: len, duration: 0.28, ease: 'power2.in' })
    .set(path, { strokeDashoffset: -len })
    .to(path, { strokeDashoffset: 0, duration: 0.55, ease: 'power3.out' })
    .fromTo(c.value, { scale: 1 }, { scale: 1.45, duration: 0.16, ease: 'power2.out', yoyo: true, repeat: 1 }, '-=0.12')
    .to(a.value, { y: -1.4, duration: 0.15, ease: 'power2.out', yoyo: true, repeat: 1 }, 0)
    .set(path, { clearProps: 'strokeDasharray,strokeDashoffset' })
}

// Los nodos laten en secuencia, de origen a destino, como un pulso que baja por la rama.
function mergeBeat() {
  return gsap
    .timeline()
    .to(a.value, { scale: 1.35, duration: 0.14, ease: 'power2.out', yoyo: true, repeat: 1 })
    .to(b.value, { strokeWidth: 2.9, duration: 0.16, ease: 'power2.out', yoyo: true, repeat: 1 }, 0.12)
    .fromTo(c.value, { scale: 1 }, { scale: 1.5, duration: 0.15, ease: 'power2.out', yoyo: true, repeat: 1 }, 0.26)
    .to(a.value, { scale: 1.15, duration: 0.12, ease: 'power2.out', yoyo: true, repeat: 1 }, 0.6)
    .set(b.value, { clearProps: 'strokeWidth' })
}

// Un libro sale del estante, se asoma y vuelve a su lugar.
function libPull(big = false) {
  return gsap
    .timeline()
    .to(b.value, { y: big ? -5 : -3.6, rotation: big ? -6 : -4, duration: 0.32, ease: 'back.out(2)' })
    .to(a.value, { rotation: -3, duration: 0.25, ease: 'power2.out' }, 0.08)
    .to(c.value, { rotation: -8, duration: 0.3, ease: 'power2.out' }, 0.08)
    .to(b.value, { y: 0, rotation: 0, duration: 0.6, ease: 'bounce.out' }, big ? 0.7 : 0.55)
    .to(a.value, { rotation: 0, duration: 0.7, ease: 'elastic.out(1.1, 0.4)' }, '<0.1')
    .to(c.value, { rotation: 0, duration: 0.9, ease: 'elastic.out(1.2, 0.35)' }, '<')
}

// Los libros se acomodan en cascada y el inclinado se termina de apoyar.
function libCascade() {
  return gsap
    .timeline()
    .to([a.value, b.value], { y: -2.4, duration: 0.18, ease: 'power2.out', stagger: 0.1 })
    .to([a.value, b.value], { y: 0, duration: 0.55, ease: 'bounce.out', stagger: 0.1 }, 0.18)
    .to(c.value, { rotation: -14, duration: 0.3, ease: 'power2.out' }, 0.3)
    .to(c.value, { rotation: 0, duration: 0.9, ease: 'elastic.out(1.2, 0.35)' })
}

// El libro inclinado se cae hacia afuera y vuelve a enderezarse con rebote.
function libTopple() {
  return gsap
    .timeline()
    .to(c.value, { rotation: 6, duration: 0.18, ease: 'power1.out' })
    .to(c.value, { rotation: 38, duration: 0.3, ease: 'power2.in' })
    .to(c.value, { rotation: 0, duration: 1.1, ease: 'elastic.out(1.1, 0.3)' }, '+=0.12')
    .to(b.value, { x: 0.8, duration: 0.12, ease: 'power2.out', yoyo: true, repeat: 1 }, 0.5)
}

// Al entrar a la Biblioteca: un libro sale bien afuera, el inclinado se cae y todo vuelve a su lugar.
function libActive() {
  return gsap
    .timeline()
    .to(b.value, { y: -5, rotation: -6, duration: 0.32, ease: 'back.out(2)' })
    .to(a.value, { rotation: -4, duration: 0.25, ease: 'power2.out' }, 0.06)
    .to(c.value, { rotation: 38, duration: 0.34, ease: 'power2.in' }, 0.12)
    .to(b.value, { y: 0, rotation: 0, duration: 0.6, ease: 'bounce.out' }, 0.62)
    .to(a.value, { rotation: 0, duration: 0.7, ease: 'elastic.out(1.1, 0.4)' }, 0.7)
    .to(c.value, { rotation: 0, duration: 1.1, ease: 'elastic.out(1.1, 0.3)' }, 0.62)
}

function play(tl: gsap.core.Timeline | gsap.core.Tween, force = false) {
  if (current?.isActive()) {
    if (!force) return current
    current.progress(1).kill()
  }
  current = tl
  return tl
}

function react(kind: 'active' | 'hover') {
  if (props.name === 'merge') {
    if (kind === 'active') {
      gsap.fromTo(root.value, { scale: 0.82 }, { scale: 1, duration: 0.8, ease: 'elastic.out(1.2, 0.4)', transformOrigin: '50% 50%' })
      return play(mergeCommit(true), true)
    }
    return play(pick([mergeRedraw, mergeBeat])())
  }
  if (props.name === 'library') {
    if (kind === 'active') {
      gsap.fromTo(root.value, { scale: 0.85 }, { scale: 1, duration: 0.8, ease: 'elastic.out(1.2, 0.4)', transformOrigin: '50% 50%' })
      return play(libActive(), true)
    }
    return play(libPull())
  }
  return fidget()
}

function fidget() {
  if (props.name === 'board') {
    const card = gsap.utils.random([a.value, b.value, c.value])
    return gsap
      .timeline()
      .to(card, { y: -2.2, duration: 0.18, ease: 'power2.out' })
      .to(card, { y: 0, duration: 0.6, ease: 'bounce.out' })
  }
  if (props.name === 'merge') return play(pick([mergeCommit, mergeRedraw, mergeBeat])())
  if (props.name === 'library') return play(pick([libPull, libCascade, libTopple])())
  minute += 360
  return gsap.to(b.value, { rotation: minute, duration: 0.9, ease: 'power3.inOut', overwrite: 'auto' })
}

function scheduleIdle(delay: number) {
  idle = gsap.delayedCall(delay, () => {
    fidget()
    scheduleIdle(gsap.utils.random(props.active ? 4 : 6, props.active ? 7 : 11))
  })
}

function startTick() {
  if (tick || props.name !== 'clock') return
  tick = gsap.delayedCall(1.4, () => {
    tick = null
    minute += 30
    hour += 2.5
    gsap.to(b.value, { rotation: minute, duration: 0.45, ease: 'back.out(3)' })
    gsap.to(a.value, { rotation: hour, duration: 0.45, ease: 'back.out(2)' })
    startTick()
  })
}

let hoverTarget: Element | null = null
function onHover() {
  if (isSoft() || !finePointer()) return
  run(() => react('hover'))
}

function stop() {
  idle?.kill()
  tick?.kill()
  idle = tick = null
}

function apply() {
  stop()
  if (isSoft()) return
  run(() => {
    scheduleIdle(gsap.utils.random(1.5, 5))
    startTick()
  })
}

onMounted(() => {
  run(() => {
    if (props.name === 'board') gsap.set([a.value, b.value, c.value], { svgOrigin: '12 20' })
    if (props.name === 'library') {
      gsap.set(a.value, { svgOrigin: '6 20' })
      gsap.set(b.value, { svgOrigin: '13 20' })
      gsap.set(c.value, { svgOrigin: '21.2 18.7' })
    }
    if (props.name === 'merge') {
      gsap.set(a.value, { svgOrigin: '6.5 5.5' })
      gsap.set(c.value, { svgOrigin: '17.5 17.5' })
    }
    if (props.name === 'clock') {
      gsap.set([a.value, b.value], { svgOrigin: '12 12' })
      gsap.set(a.value, { rotation: hour })
    }
  })
  apply()
  hoverTarget = props.name === 'merge' || props.name === 'library' ? (root.value?.closest('button, a') as HTMLElement | null) ?? root.value : null
  hoverTarget?.addEventListener('mouseenter', onHover)
})
onBeforeUnmount(() => {
  stop()
  hoverTarget?.removeEventListener('mouseenter', onHover)
})

watch(soft, apply)
watch(
  () => props.active,
  (on) => {
    if (!on || isSoft()) return
    run(() => react('active'))
  },
)
</script>

<template>
  <svg
    ref="root"
    class="navmark"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.9"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'board'">
      <rect ref="a" x="3.5" y="4" width="7" height="16" rx="1.8" />
      <rect ref="b" x="13.5" y="4" width="7" height="9" rx="1.8" />
      <rect ref="c" x="13.5" y="16" width="7" height="4" rx="1.4" />
    </template>
    <template v-else-if="name === 'clock'">
      <circle cx="12" cy="12" r="8.5" />
      <path ref="a" d="M12 12V9" />
      <path ref="b" d="M12 12V6.8" />
      <circle cx="12" cy="12" r="0.6" fill="currentColor" stroke="none" />
    </template>
    <template v-else-if="name === 'merge'">
      <circle ref="a" cx="6.5" cy="5.5" r="2.2" />
      <path d="M6.5 7.7v12.8" />
      <path ref="b" d="M6.5 8.5a9 9 0 0 0 8.8 9" />
      <circle ref="c" cx="17.5" cy="17.5" r="2.2" />
      <circle ref="d" cx="0" cy="0" r="2.3" fill="currentColor" stroke="none" opacity="0" />
    </template>
    <template v-else>
      <rect ref="a" x="3.5" y="4" width="5" height="16" rx="1.4" />
      <rect ref="b" x="10.5" y="4" width="5" height="16" rx="1.4" />
      <path ref="c" d="m18.2 6 3 12.7" />
    </template>
  </svg>
</template>

<style scoped>
.navmark {
  display: block;
  flex: none;
  overflow: visible;
}
</style>
