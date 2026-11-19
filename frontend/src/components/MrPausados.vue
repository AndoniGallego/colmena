<script setup lang="ts">
import type { Mr } from '../api/mrsApi'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import MrCard from './MrCard.vue'

defineProps<{ items: Mr[]; now: number }>()
defineEmits<{ open: [ref: string] }>()
const open = defineModel<boolean>('open', { default: false })
const { run } = useGsap()

function toggle() {
  haptic(5)
  open.value = !open.value
}

function enter(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.18, onComplete: done }))
  run(() => {
    gsap.fromTo(el, { height: 0, opacity: 0 }, { height: 'auto', opacity: 1, duration: 0.45, ease: 'power3.out', clearProps: 'height,opacity', onComplete: done })
    gsap.from(el.querySelectorAll('.card'), { y: 10, opacity: 0, duration: 0.4, ease: 'power3.out', stagger: 0.04, delay: 0.05, clearProps: 'transform,opacity' })
  })
}
function leave(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
  run(() => gsap.to(el, { height: 0, opacity: 0, duration: 0.3, ease: 'power3.in', onComplete: done }))
}
</script>

<template>
  <div v-if="items.length" class="pausa">
    <button type="button" class="pausa-toggle" :aria-expanded="open" @click="toggle">
      <Icon name="pause" :size="12" class="ico" />
      <span>{{ open ? `Ocultar en pausa (${items.length})` : `Ver en pausa (${items.length})` }}</span>
      <Icon name="chevron" :size="14" class="chev" :class="{ open }" />
    </button>
    <Transition :css="false" @enter="enter" @leave="leave">
      <ul v-if="open" class="items">
        <li v-for="m in items" :key="m.ref">
          <MrCard :m="m" :now="now" pausado @open="$emit('open', $event)" />
        </li>
      </ul>
    </Transition>
  </div>
</template>

<style scoped>
.pausa { display: grid; grid-template-columns: minmax(0, 1fr); }
.pausa-toggle { width: 100%; display: inline-flex; align-items: center; justify-content: center; gap: 8px; min-height: 40px; margin-top: 4px; padding: 8px 12px; border-radius: var(--r-lg); font-size: 13px; font-weight: 560; color: var(--text-3); background: transparent; border: 1px dashed var(--line-2); transition: background 0.2s, color 0.2s, border-color 0.2s, scale 0.3s var(--spring); }
.pausa-toggle:hover { background: var(--surface-2); color: var(--text-2); border-color: var(--line); }
.pausa-toggle:active { scale: 0.98; }
.ico { color: var(--text-4); }
.chev { color: var(--text-4); transition: transform 0.4s var(--spring); transform: rotate(90deg); }
.chev.open { transform: rotate(-90deg); }
.items { list-style: none; margin: 0 -4px; padding: 10px 4px 4px; display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; overflow: hidden; }
@media (prefers-reduced-motion: reduce) { .chev, .pausa-toggle { transition: none; } }
</style>
