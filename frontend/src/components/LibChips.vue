<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import type { LibItem } from '../api/types'
import { KIND_LABEL, safeClaudeUrl } from '../lib/biblioteca'
import { cachedLibItem, openInLibrary, openOverlay } from '../state/biblioteca'
import Icon from './Icon.vue'

const props = defineProps<{ ids: string[]; /** one single "Abrir en Biblioteca" chip per message; flows have their own icon */ library?: boolean }>()

const items = ref<LibItem[]>([])

async function load() {
  const got = await Promise.all(props.ids.map(cachedLibItem))
  items.value = got.filter((i): i is LibItem => !!i)
}
onMounted(load)
watch(() => props.ids.join(), load)

const thumbs = computed(() => items.value.filter((i) => i.kind === 'image' && i.src).slice(0, 4))
const extra = computed(() => Math.max(0, items.value.filter((i) => i.kind === 'image' && i.src).length - 4))
const rest = computed(() => {
  const r = items.value.filter((i) => !thumbs.value.includes(i))
  // flows open from the icon inside their own card
  return props.library ? r.filter((i) => i.kind !== 'diagrama').slice(0, 1) : r
})
const label = (i: LibItem) => (i.kind === 'html' ? i.title || 'Página' : i.kind === 'diagrama' ? i.title || KIND_LABEL[i.kind] : i.title || i.nombre || KIND_LABEL[i.kind])
</script>

<template>
  <div v-if="items.length" class="chips">
    <div v-if="thumbs.length" class="strip">
      <button v-for="t in thumbs" :key="t.id" class="thumb" :title="label(t)" @click="openOverlay(t.id)">
        <img :src="t.src" :alt="label(t)" loading="lazy" decoding="async" />
      </button>
      <span v-if="extra" class="more mono">+{{ extra }}</span>
    </div>
    <div v-for="i in rest" :key="i.id" class="row">
      <button v-if="!library" class="chip main" @click="openOverlay(i.id)">
        <Icon :name="i.kind === 'diagrama' ? 'diagrama' : i.kind === 'html' ? 'library' : 'doc'" :size="13" />
        Ver en la app
        <span class="what">{{ label(i) }}</span>
      </button>
      <button v-else class="chip main" @click="openInLibrary(i.id)"><Icon name="library" :size="13" /> Abrir en Biblioteca</button>
      <a v-if="safeClaudeUrl(i.url)" class="chip" :href="safeClaudeUrl(i.url)" target="_blank" rel="noopener noreferrer"><Icon name="external" :size="12" /> Abrir en claude.ai</a>
    </div>
  </div>
</template>

<style scoped>
.chips {
  display: grid;
  gap: 5px;
  justify-items: start;
  margin: 4px 0 2px;
  min-width: 0;
}
.row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-width: 100%;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 100%;
  height: 26px;
  padding: 0 11px 0 9px;
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: 540;
  color: var(--text-2);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: color 0.2s, background 0.2s, box-shadow 0.2s, scale 0.35s var(--spring);
}
.chip.main {
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.chip:hover {
  scale: 1.03;
  box-shadow: inset 0 0 0 1px var(--accent);
}
.chip:active {
  scale: var(--press-scale);
}
.what {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--text-3);
  font-weight: 460;
}
.strip {
  display: flex;
  align-items: center;
  gap: 6px;
}
.thumb {
  width: 76px;
  height: 56px;
  border-radius: var(--r-md);
  overflow: hidden;
  background: var(--surface);
  box-shadow: 0 0 0 1px var(--line-2);
  transition: scale 0.35s var(--spring), box-shadow 0.25s;
}
.thumb:hover {
  scale: 1.05;
  box-shadow: 0 0 0 1px var(--accent-line), 0 10px 24px -12px var(--accent);
}
.thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}
.more {
  font-size: 11px;
  color: var(--text-3);
}
</style>
