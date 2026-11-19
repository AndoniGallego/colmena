<script setup lang="ts">
import { ref } from 'vue'
import { ACCEPT } from '../lib/attachments'
import Icon from './Icon.vue'

defineProps<{ disabled?: boolean; count?: number }>()
const emit = defineEmits<{ pick: [files: File[]] }>()
const input = ref<HTMLInputElement | null>(null)

function onChange(e: Event) {
  const el = e.target as HTMLInputElement
  const files = Array.from(el.files ?? [])
  el.value = ''
  if (files.length) emit('pick', files)
}
</script>

<template>
  <button type="button" class="clip keycap" :class="{ has: !!count }" :disabled="disabled" aria-label="Adjuntar archivo" @click.stop="input?.click()">
    <Icon name="clip" :size="17" />
    <span v-if="count" class="badge mono">{{ count }}</span>
  </button>
  <input ref="input" type="file" multiple :accept="ACCEPT" tabindex="-1" hidden @change="onChange" />
</template>

<style scoped>
.clip {
  position: relative;
  flex: none;
  width: 44px;
  min-height: 44px;
  align-self: stretch;
  display: grid;
  place-items: center;
  color: var(--text-3);
}
.clip :deep(svg) {
  transition: rotate 0.4s var(--spring);
}
.clip:hover:not(:disabled) {
  color: var(--text);
}
.clip:hover:not(:disabled) :deep(svg) {
  rotate: -12deg;
}
@media (min-width: 1024px) {
  .clip { width: 40px; min-height: 40px; }
}
.clip.has {
  color: var(--accent);
}
.clip:disabled {
  opacity: 0.35;
  cursor: default;
}
.badge {
  position: absolute;
  top: 4px;
  right: 3px;
  min-width: 15px;
  height: 15px;
  padding: 0 4px;
  border-radius: var(--r-pill);
  font-size: 9.5px;
  line-height: 15px;
  text-align: center;
  background: var(--accent);
  color: var(--accent-ink);
  animation: badge-pop 0.5s var(--spring);
}
@keyframes badge-pop {
  from { transform: scale(0); }
}
</style>
