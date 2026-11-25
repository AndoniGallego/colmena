<script setup lang="ts">
import { computed } from 'vue'
import { cartel } from '../state/cartel'

const MITAD = 120
const left = computed(() => {
  const ancho = typeof window === 'undefined' ? 1200 : window.innerWidth
  return Math.min(Math.max(cartel.x, MITAD + 8), Math.max(MITAD + 8, ancho - MITAD - 8))
})
</script>

<template>
  <Teleport to="body">
    <Transition name="cartel">
      <div v-if="cartel.visible" class="cartel" role="tooltip" :style="{ left: `${left}px`, top: `${cartel.y + 8}px` }">
        <b>{{ cartel.nombre }}</b>
        <span>{{ cartel.desc }}</span>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cartel {
  position: fixed;
  z-index: 60;
  translate: -50% 0;
  display: grid;
  gap: 2px;
  width: max-content;
  max-width: 240px;
  padding: 7px 10px;
  border-radius: var(--r-md);
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.28);
  font-size: var(--t-sm);
  line-height: 1.35;
  color: var(--text-2);
  text-wrap: pretty;
  pointer-events: none;
  transform-origin: top center;
}
.cartel b {
  color: var(--text);
  font-weight: 600;
}
.cartel-enter-active {
  transition: opacity 0.12s var(--ease-out), transform 0.12s var(--ease-out);
}
.cartel-leave-active {
  transition: opacity 0.08s linear;
}
.cartel-enter-from {
  opacity: 0;
  transform: translateY(-3px) scale(0.97);
}
.cartel-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .cartel-enter-active,
  .cartel-leave-active {
    transition: none;
  }
}
</style>
