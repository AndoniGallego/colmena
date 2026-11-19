<script setup lang="ts" generic="T extends string | number">
import { computed } from 'vue'

const props = defineProps<{
  modelValue: T
  options: { value: T; label: string; disabled?: boolean }[]
  label: string
  disabled?: boolean
}>()
const emit = defineEmits<{ 'update:modelValue': [value: T] }>()

const index = computed(() => Math.max(0, props.options.findIndex((o) => o.value === props.modelValue)))
</script>

<template>
  <div class="seg" role="radiogroup" :aria-label="label" :style="{ '--n': options.length, '--i': index }">
    <i class="seg-knob" aria-hidden="true" />
    <button
      v-for="o in options"
      :key="String(o.value)"
      class="seg-btn"
      role="radio"
      :aria-checked="o.value === modelValue"
      :disabled="disabled || o.disabled"
      @click="emit('update:modelValue', o.value)"
    >
      {{ o.label }}
    </button>
  </div>
</template>

<style scoped>
.seg {
  position: relative;
  display: grid;
  grid-template-columns: repeat(var(--n), 1fr);
  padding: 3px;
  border-radius: var(--r-md);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.seg-knob {
  position: absolute;
  top: 3px;
  bottom: 3px;
  left: 3px;
  width: calc((100% - 6px) / var(--n));
  border-radius: 8px;
  background: var(--accent);
  box-shadow: 0 4px 14px -6px var(--accent);
  translate: calc(var(--i) * 100%) 0;
  transition: translate 0.5s var(--spring);
}
.seg-btn {
  position: relative;
  z-index: 1;
  min-height: max(36px, var(--h-md));
  padding: 0 12px;
  font-size: 13px;
  font-weight: 580;
  color: var(--text-3);
  transition: color 0.25s, scale 0.3s var(--spring);
}
.seg-btn:hover:not(:disabled) { color: var(--text); }
.seg-btn:active:not(:disabled) { scale: var(--press-scale); }
.seg-btn[aria-checked='true'] { color: var(--accent-ink); }
.seg-btn:disabled { opacity: 0.55; cursor: default; }
:root[data-motion='soft'] .seg-knob { transition: translate 0.15s linear; }
</style>
