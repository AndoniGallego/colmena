<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { gsap, isSoft, soft, useGsap } from '../motion'

const props = defineProps<{ on: boolean }>()

const { run } = useGsap()
const fill = ref<HTMLElement | null>(null)
const shine = ref<HTMLElement | null>(null)
const halo = ref<HTMLElement | null>(null)
let breathe: gsap.core.Tween | null = null

function stopBreathe() {
  breathe?.kill()
  breathe = null
}

// Respira lento: apenas sube y baja el brillo, para que se note viva sin llamar la atención.
function startBreathe() {
  stopBreathe()
  if (isSoft()) return
  breathe = gsap.fromTo(halo.value, { opacity: 0.35 }, { opacity: 0.9, duration: 2.6, ease: 'sine.inOut', repeat: -1, yoyo: true })
}

function show(animate: boolean) {
  gsap.killTweensOf([fill.value, shine.value, halo.value])
  if (!animate || isSoft()) {
    gsap.set([fill.value, halo.value], { scaleY: 1 })
    gsap.set(shine.value, { opacity: 0 })
    if (animate) gsap.fromTo(fill.value, { opacity: 0 }, { opacity: 1, duration: 0.25 })
    else gsap.set(fill.value, { opacity: 1 })
    gsap.set(halo.value, { opacity: isSoft() ? 0.6 : 0.35 })
    startBreathe()
    return
  }
  const h = fill.value?.offsetHeight ?? 40
  gsap
    .timeline({ onComplete: startBreathe })
    .set(fill.value, { opacity: 1 })
    .fromTo([fill.value, halo.value], { scaleY: 0 }, { scaleY: 1, duration: 0.9, ease: 'elastic.out(1, 0.6)' }, 0)
    .fromTo(halo.value, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'power2.out' }, 0.05)
    .to(halo.value, { opacity: 0.35, duration: 0.8, ease: 'power2.inOut' }, 0.6)
    .fromTo(shine.value, { y: -28, opacity: 1 }, { y: h, duration: 0.7, ease: 'power2.inOut' }, 0.22)
    .set(shine.value, { opacity: 0 })
}

function hide() {
  stopBreathe()
  gsap.killTweensOf([fill.value, shine.value, halo.value])
  if (isSoft()) {
    gsap.to([fill.value, halo.value], { opacity: 0, duration: 0.2 })
    return
  }
  gsap.to([fill.value, halo.value], { scaleY: 0, opacity: 0, duration: 0.22, ease: 'power2.in' })
  gsap.to(shine.value, { opacity: 0, duration: 0.18 })
}

onMounted(() => run(() => (props.on ? show(false) : gsap.set([fill.value, halo.value, shine.value], { opacity: 0, scaleY: 0 }))))
onBeforeUnmount(stopBreathe)
watch(
  () => props.on,
  (on) => run(() => (on ? show(true) : hide())),
)
watch(soft, () => {
  if (props.on) run(() => show(false))
})
</script>

<template>
  <i class="tabline" aria-hidden="true">
    <i ref="halo" class="halo" />
    <i ref="fill" class="fill"><i ref="shine" class="shine" /></i>
  </i>
</template>

<style scoped>
.tabline {
  position: absolute;
  z-index: 1;
  left: 0;
  top: 10px;
  bottom: 0;
  width: 2px;
  pointer-events: none;
}
.fill,
.halo {
  position: absolute;
  inset: 0;
  border-radius: 2px;
  transform-origin: 50% 50%;
}
.fill {
  overflow: hidden;
  background: var(--accent);
}
.halo {
  box-shadow: 0 0 8px color-mix(in srgb, var(--accent) 55%, transparent), 0 0 2px var(--accent);
}
.shine {
  position: absolute;
  left: 0;
  top: 0;
  width: 100%;
  height: 28px;
  opacity: 0;
  background: linear-gradient(transparent, color-mix(in srgb, white 85%, var(--accent)), transparent);
}
</style>
