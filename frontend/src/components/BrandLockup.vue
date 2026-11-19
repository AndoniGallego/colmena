<script setup lang="ts">
import BrandMark from './BrandMark.vue'

withDefaults(defineProps<{ size?: number; working?: boolean; attention?: boolean; live?: boolean; intro?: boolean; active?: number }>(), {
  size: 28,
  live: true,
  intro: true,
})
</script>

<template>
  <span class="lockup" :style="{ '--s': `${size}px` }">
    <BrandMark :size="size" :working="working" :attention="attention" :live="live" :intro="intro" :active="active" />
    <span class="word">colmena</span>
  </span>
</template>

<style scoped>
.lockup {
  display: inline-flex;
  align-items: center;
  gap: calc(var(--s) * 0.3);
}
.word {
  font-family: var(--font-display);
  font-weight: 700;
  font-size: calc(var(--s) * 0.68);
  letter-spacing: -0.035em;
  line-height: 1;
  color: var(--text);
}
</style>
