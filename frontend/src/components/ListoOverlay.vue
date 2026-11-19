<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { gsap, haptic, isSoft, useGsap } from '../motion'

const props = defineProps<{ texto: string; visible: boolean }>()
const { run } = useGsap()
const check = ref<SVGPathElement | null>(null)

function animarCheck() {
  if (!props.visible || !check.value || isSoft()) return
  run(() => gsap.fromTo(check.value, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.5, ease: 'power2.out' }))
}

watch(
  () => props.visible,
  async (on) => {
    if (!on) return
    haptic(10)
    await nextTick()
    animarCheck()
  },
)

onMounted(() => {
  if (props.visible) void nextTick().then(animarCheck)
})
</script>

<template>
  <Transition name="ok">
    <div v-if="visible" class="listo" role="status">
      <svg viewBox="0 0 48 48" width="64" height="64" fill="none" stroke="currentColor" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <circle cx="24" cy="24" r="20" class="ring" />
        <path ref="check" d="M14 25l7 7 13-15" />
      </svg>
      <p>{{ texto }}</p>
    </div>
  </Transition>
</template>

<style scoped>
.listo {
  position: absolute;
  inset: 0;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 10px;
  background: color-mix(in srgb, var(--surface) 94%, transparent);
  color: var(--st-done);
  z-index: 2;
}
.listo p {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}
.ring {
  stroke-opacity: 0.35;
}
.ok-enter-active {
  transition: opacity 0.25s;
}
.ok-leave-active {
  transition: opacity 0.2s;
}
.ok-enter-from,
.ok-leave-to {
  opacity: 0;
}
</style>
