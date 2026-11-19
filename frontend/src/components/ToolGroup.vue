<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { toolLine, type IndexedItem } from '../lib/transcript'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import LibChips from './LibChips.vue'

const props = defineProps<{ tools: IndexedItem[]; live?: boolean; quiet?: boolean }>()

const COLLAPSE_FROM = 3
const open = ref(false)
const root = ref<HTMLElement | null>(null)
const list = ref<HTMLElement | null>(null)

const lines = computed(() => props.tools.map((t) => ({ key: t.idx, ...toolLine(t.name, t.summary) })))
const foldable = computed(() => lines.value.length >= COLLAPSE_FROM)
const shown = computed(() => (foldable.value && !open.value ? lines.value.slice(-1) : lines.value))
const hidden = computed(() => lines.value.length - 1)
const libIds = computed(() => [...new Set(props.tools.flatMap((t) => t.lib_ids ?? []))])

const { run } = useGsap()

async function toggle() {
  open.value = !open.value
  await nextTick()
  if (!open.value || isSoft() || !list.value) return
  run(() => gsap.from(list.value!.querySelectorAll('li:not(:last-child)'), { opacity: 0, x: -10, duration: 0.4, ease: 'power3.out', stagger: 0.025 }))
}

onMounted(() => {
  if (!root.value || props.quiet) return
  if (isSoft()) run(() => gsap.from(root.value, { opacity: 0, duration: 0.25 }))
  else run(() => gsap.from(root.value, { opacity: 0, x: -8, duration: 0.5, ease: 'power3.out', delay: 0.05 }))
})
</script>

<template>
  <div ref="root" class="tools" :class="{ live }">
    <ul ref="list" class="lines">
      <li v-for="(l, i) in shown" :key="l.key" :class="{ last: i === shown.length - 1 }">
        <Icon :name="l.icon" :size="12" />
        <span class="verb">{{ l.verb }}</span>
        <span class="target mono" :title="l.target">{{ l.target }}</span>
      </li>
    </ul>
    <button v-if="foldable" type="button" class="more mono" :aria-expanded="open" @click.stop="toggle">
      <Icon name="chevron" :size="11" :class="{ flip: open }" />
      {{ open ? 'Ocultar' : `+${hidden} acciones` }}
    </button>
    <LibChips v-if="libIds.length" :ids="libIds" />
  </div>
</template>

<style scoped>
.tools {
  margin: 2px 0 6px 26px;
  padding-left: 12px;
  border-left: 1px dashed var(--line-2);
  display: grid;
  gap: 3px;
  justify-items: start;
  min-width: 0;
}
.lines {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 2px;
  max-width: 100%;
}
li {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
  font-size: 12px;
  line-height: 1.7;
  color: var(--text-3);
}
li svg {
  flex: none;
  color: var(--text-4);
}
.verb {
  flex: none;
}
.target {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--t-sm);
  color: var(--text-4);
}
.live li.last svg {
  color: var(--accent);
}
.live li.last .verb {
  color: var(--text-2);
}
.more {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 22px;
  padding: 0 8px 0 5px;
  border-radius: var(--r-pill);
  font-size: 11px;
  color: var(--text-3);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: color 0.2s, background 0.2s, scale 0.35s var(--spring);
}
.more:hover {
  color: var(--text);
  background: var(--surface-hover);
}
.more:active {
  scale: var(--press-scale);
}
.more svg {
  transition: rotate 0.35s var(--spring);
}
.more svg.flip {
  rotate: 90deg;
}
</style>
