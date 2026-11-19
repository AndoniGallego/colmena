<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Attachment } from '../state/attachments'
import { extOf, formatSize, uploadSrc } from '../lib/attachments'
import { haptic, isSoft, ring } from '../motion'
import Icon from './Icon.vue'

const props = defineProps<{ item: Attachment }>()
defineEmits<{ remove: []; retry: [] }>()

const thumb = ref<HTMLElement | null>(null)
const blobBroken = ref(false)
const remoteBroken = ref(false)

// El blob local sale primero; si el navegador no lo puede pintar, se cae al archivo ya subido.
const src = computed(() => {
  if (props.item.kind !== 'image') return ''
  if (props.item.preview && !blobBroken.value) return props.item.preview
  return props.item.id && !remoteBroken.value ? uploadSrc(props.item.id) : ''
})
const C = 2 * Math.PI * 14

watch(
  () => props.item.status,
  (st, prev) => {
    if (st !== 'ready' || prev !== 'uploading' || isSoft() || !thumb.value) return
    ring(thumb.value, getComputedStyle(thumb.value).getPropertyValue('--st-done'), 56)
    haptic(10)
  },
)
</script>

<template>
  <li class="chip" :data-st="item.status" :style="{ '--p': item.status === 'ready' ? 1 : item.progress }">
    <span ref="thumb" class="thumb">
      <img v-if="src" :src="src" alt="" @error="item.preview && !blobBroken ? (blobBroken = true) : (remoteBroken = true)" />
      <span v-else class="fallback">
        <Icon :name="item.kind === 'image' ? 'image' : 'doc'" :size="20" />
        <b class="ext mono">{{ extOf(item.name) }}</b>
      </span>
      <span v-if="item.status === 'uploading'" class="veil">
        <svg viewBox="0 0 32 32" width="30" height="30" aria-hidden="true">
          <circle class="track" cx="16" cy="16" r="14" />
          <circle class="arc" cx="16" cy="16" r="14" :stroke-dasharray="C" :stroke-dashoffset="C * (1 - Math.max(0.06, item.progress))" />
        </svg>
      </span>
      <button v-else-if="item.status === 'error'" type="button" class="veil err" :aria-label="`Reintentar subida de ${item.name}`" @click.stop="$emit('retry')">
        <Icon name="refresh" :size="18" />
      </button>
      <span v-else class="ok"><Icon name="check" :size="10" /></span>
    </span>
    <button type="button" class="x" :aria-label="`Quitar ${item.name}`" @click.stop="$emit('remove')"><Icon name="close" :size="11" /></button>
    <span class="name">{{ item.name }}</span>
    <span class="meta mono">{{ item.status === 'error' ? item.error : formatSize(item.size) }}</span>
  </li>
</template>

<style scoped>
.chip {
  --c: var(--accent);
  position: relative;
  flex: none;
  width: 64px;
  display: grid;
  gap: 1px;
  scroll-snap-align: start;
}
.chip[data-st='ready'] { --c: var(--st-done); }
.chip[data-st='error'] { --c: var(--danger); }
.thumb {
  position: relative;
  width: 64px;
  height: 64px;
  margin-bottom: 4px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  overflow: hidden;
  color: var(--text-3);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: box-shadow 0.3s;
}
.chip[data-st='error'] .thumb {
  box-shadow: inset 0 0 0 1.5px var(--danger);
}
.thumb img {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.fallback {
  display: grid;
  justify-items: center;
  gap: 2px;
}
.ext {
  font-size: 9.5px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.veil {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: color-mix(in srgb, var(--bg) 55%, transparent);
  -webkit-backdrop-filter: blur(1.5px);
  backdrop-filter: blur(1.5px);
  color: var(--text);
}
.veil.err {
  color: var(--danger);
  background: color-mix(in srgb, var(--bg) 62%, transparent);
}
.veil svg {
  transform: rotate(-90deg);
}
.track,
.arc {
  fill: none;
  stroke-width: 3;
}
.track {
  stroke: color-mix(in srgb, var(--text) 18%, transparent);
}
.arc {
  stroke: var(--accent);
  stroke-linecap: round;
  transition: stroke-dashoffset 0.25s var(--ease-out);
}
.ok {
  position: absolute;
  left: 4px;
  bottom: 4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: var(--st-done);
  color: var(--bg);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--bg) 70%, transparent);
  animation: pop 0.55s var(--spring);
}
@keyframes pop {
  from { transform: scale(0) rotate(-90deg); }
}
.x {
  position: absolute;
  top: -5px;
  right: -5px;
  z-index: 1;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--text);
  background: var(--surface-hover);
  box-shadow: 0 0 0 2px var(--surface), inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, scale 0.3s var(--spring);
}
.x::after {
  content: '';
  position: absolute;
  inset: -12px;
}
.x:hover { background: var(--danger-soft); color: var(--danger); }
.x:active { scale: var(--press-scale); }
.name,
.meta {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.name {
  font-size: 11px;
  line-height: 1.3;
  color: var(--text-2);
}
.meta {
  font-size: 9.5px;
  line-height: 1.2;
  color: var(--text-3);
}
.chip[data-st='error'] .meta { color: var(--danger); }
</style>
