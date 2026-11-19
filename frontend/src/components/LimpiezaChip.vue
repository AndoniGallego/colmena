<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { chipLabel } from '../lib/limpieza'
import { gsap, isSoft, useGsap } from '../motion'
import { abrirLimpieza, libres } from '../state/limpieza'
import Icon from './Icon.vue'

const { run } = useGsap()
const shown = ref(false)

/** Aparece una sola vez con un fundido; sin pulso ni contador. */
function enter(node: Element, done: () => void) {
  if (isSoft() || shown.value) return done()
  shown.value = true
  run(() => gsap.fromTo(node, { y: 8, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: 'power3.out', clearProps: 'transform,opacity', onComplete: done }))
}
onMounted(() => (shown.value = false))
</script>

<template>
  <Transition :css="false" @enter="enter">
    <button v-if="libres.length" type="button" class="lchip" @click="abrirLimpieza()">
      <Icon name="broom" :size="14" />
      <span>{{ chipLabel(libres.length) }}</span>
      <Icon name="chevron" :size="12" class="arr" />
    </button>
  </Transition>
</template>

<style scoped>
.lchip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  max-width: 100%;
  margin: 0;
  padding: 0 14px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}
.lchip:hover {
  color: var(--text);
  border-color: color-mix(in srgb, var(--accent) 50%, transparent);
}
.arr {
  opacity: 0.6;
}
</style>
