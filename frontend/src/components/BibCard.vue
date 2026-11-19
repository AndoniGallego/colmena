<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { LibItem } from '../api/types'
import { diagramaOf, cardVariant, coverHues, formatSize, KIND_LABEL, safeClaudeUrl } from '../lib/biblioteca'
import { clock } from '../lib/time'
import { gsap, isSoft, useGsap } from '../motion'
import BibFrame from './BibFrame.vue'
import DiagramaCard from './DiagramaCard.vue'
import Icon from './Icon.vue'

const props = defineProps<{
  item: LibItem
  layout: 'grid' | 'list'
  selected?: boolean
  fresh?: boolean
  preview?: boolean
  index: number
  tab?: boolean
  selecting?: boolean
  checked?: boolean
  leaving?: boolean
}>()
defineEmits<{ open: []; full: []; enter: []; leave: []; quitar: []; toggle: [range: boolean] }>()

const variant = computed(() => cardVariant(props.item))
const hues = computed(() => coverHues(props.item.id))
const dot = computed(() => `hsl(${coverHues(props.item.session_id)[0]} 62% 58%)`)
const cover = computed(() => ({ '--h1': hues.value[0], '--h2': hues.value[1] }))
const when = computed(() => {
  const t = Date.parse(props.item.ts)
  return Number.isNaN(t) ? '' : clock(t)
})
const name = computed(() => props.item.title || props.item.nombre || KIND_LABEL[props.item.kind])
const claude = computed(() => safeClaudeUrl(props.item.url))
const diagrama = computed(() => (variant.value === 'diagrama' ? diagramaOf(props.item) : null))
const tip = computed(() => `${name.value} · ${props.item.session_titulo}${props.item.donde ? ` · ${props.item.donde}` : ''}`)

const root = ref<HTMLElement | null>(null)
const thumb = ref<HTMLElement | null>(null)
const scale = ref(0.2)
const offscreen = ref(false)
let io: IntersectionObserver | null = null
const { run } = useGsap()

onMounted(() => {
  if (props.item.kind === 'gif' && root.value) {
    io = new IntersectionObserver(([e]) => (offscreen.value = !e.isIntersecting), { rootMargin: '120px' })
    io.observe(root.value)
  }
})
onBeforeUnmount(() => io?.disconnect())

const gifSrc = computed(() => (props.item.kind === 'gif' && offscreen.value ? '' : props.item.src))

function measure() {
  if (thumb.value) scale.value = thumb.value.clientWidth / 1280
}
onMounted(() => props.fresh && pulse())

function pulse() {
  if (!root.value) return
  if (isSoft()) run(() => gsap.fromTo(root.value, { opacity: 0.4 }, { opacity: 1, duration: 0.2 }))
  else
    run(() =>
      gsap.fromTo(root.value, { scale: 0.94, boxShadow: '0 0 0 2px var(--accent), 0 0 34px -4px var(--accent)' }, { scale: 1, boxShadow: '0 0 0 0px transparent, 0 0 0 transparent', duration: 1.4, ease: 'elastic.out(1, 0.5)', clearProps: 'boxShadow,scale' }),
    )
}
defineExpose({ el: root, measure, pulse })
</script>

<template>
  <article
    ref="root"
    class="card"
    :class="[variant, layout, { selected, gone: variant === 'gone', fresh, leaving, picking: selecting, checked }]"
    role="gridcell"
    :aria-selected="selecting ? checked : selected"
    :aria-label="tip"
    :tabindex="tab ? 0 : -1"
    :data-idx="index"
    :data-id="item.id"
    :title="tip"
    @click="selecting ? $emit('toggle', $event.shiftKey) : $emit('open')"
    @dblclick.prevent="!selecting && $emit('full')"
    @keydown.enter.prevent.stop="$emit('enter')"
    @keydown.space.prevent.stop="selecting && $emit('toggle', $event.shiftKey)"
    @pointerenter="$emit('enter'); measure()"
    @pointerleave="$emit('leave')"
  >
    <span v-if="selecting" class="pick" :class="{ on: checked }" aria-hidden="true"><Icon name="check" :size="13" /></span>
    <button v-else type="button" class="del" aria-label="Quitar de la Biblioteca" title="Quitar de la Biblioteca (Supr)" @click.stop="$emit('quitar')" @dblclick.stop>
      <Icon name="trash" :size="14" />
    </button>
    <div ref="thumb" class="thumb" :style="cover">
      <template v-if="variant === 'image'">
        <img :src="gifSrc" :alt="name" loading="lazy" decoding="async" draggable="false" />
      </template>
      <template v-else-if="variant === 'video'">
        <video :src="`${item.src}#t=0.1`" preload="metadata" muted playsinline tabindex="-1" />
        <span class="play"><Icon name="play" :size="18" /></span>
      </template>
      <template v-else-if="variant === 'diagrama'">
        <div v-if="diagrama && layout !== 'list'" class="diagrama-mini"><DiagramaCard :diagrama="diagrama" mini /></div>
        <div v-else class="art"><Icon name="diagrama" :size="layout === 'list' ? 20 : 30" /></div>
      </template>
      <template v-else-if="variant === 'pruebas'">
        <div class="art"><span class="emoji" aria-hidden="true">🧪</span></div>
      </template>
      <template v-else-if="variant === 'cover'">
        <div class="win" aria-hidden="true"><i /><i /><i /></div>
        <b class="cover-title">{{ name }}</b>
        <code v-if="item.nombre" class="cover-file mono">{{ item.nombre }}</code>
        <BibFrame v-if="preview && item.src" class="live" preview :src="item.src" :title="name" :style="{ '--s': scale }" />
      </template>
      <template v-else-if="variant === 'remoto'">
        <div class="art"><Icon name="external" :size="28" /></div>
        <span class="art-note">Solo en claude.ai</span>
      </template>
      <template v-else>
        <div class="art"><Icon :name="item.kind === 'pdf' ? 'doc' : item.kind === 'video' ? 'film' : 'doc'" :size="30" /></div>
        <code v-if="item.nombre" class="cover-file mono">{{ item.nombre }}</code>
      </template>
      <span v-if="variant === 'gone'" class="gone-note">{{ item.motivo || 'Ya no está en disco' }}</span>
      <span class="chips">
        <b v-if="claude" class="chip">claude.ai</b>
        <b v-if="item.versions.length > 1" class="chip mono">v{{ item.version || item.versions.length }}</b>
        <b class="chip kind">{{ KIND_LABEL[item.kind] }}</b>
      </span>
    </div>
    <div class="meta">
      <b class="name">{{ name }}</b>
      <span class="sub">
        <i class="dot" :style="{ background: dot }" />
        <span class="sess">{{ item.kind === 'pruebas' && item.description ? item.description : item.session_titulo }}</span>
        <span class="when mono">{{ when }}</span>
        <span v-if="layout === 'list'" class="size mono">{{ formatSize(item.size) }}</span>
      </span>
    </div>
  </article>
</template>

<style scoped>
.card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  border-radius: var(--r-lg);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  cursor: pointer;
  outline: none;
  transition: translate 0.4s var(--spring), box-shadow 0.3s, background 0.25s;
  -webkit-tap-highlight-color: transparent;
}
.card:focus-visible {
  box-shadow: inset 0 0 0 2px var(--accent);
}
.card.selected {
  box-shadow: inset 0 0 0 2px var(--accent), 0 14px 34px -18px var(--accent);
}
.card.gone {
  opacity: 0.55;
}
@media (hover: hover) {
  .card:hover {
    translate: 0 -2px;
    background: var(--surface-hover);
    box-shadow: inset 0 0 0 1px var(--accent-line), 0 16px 34px -20px rgba(0, 0, 0, 0.6);
  }
  .card.selected:hover {
    box-shadow: inset 0 0 0 2px var(--accent), 0 16px 34px -18px var(--accent);
  }
  .del {
    opacity: 0;
  }
  .card:hover .del,
  .card:focus-within .del,
  .del:focus-visible {
    opacity: 1;
  }
  .card.image:hover img {
    scale: 1.06;
  }
}
:root[data-motion='soft'] .card:hover {
  translate: none;
}
:root[data-motion='soft'] .card.image:hover img {
  scale: none;
}
.thumb img {
  outline: 1px solid var(--img-outline);
  outline-offset: -1px;
}
.card:active {
  scale: 0.985;
}

.thumb {
  position: relative;
  aspect-ratio: 16 / 10;
  border-radius: 14px 14px 0 0;
  overflow: hidden;
  display: grid;
  place-items: center;
  background: var(--surface-2);
}
@media (max-width: 519px) {
  .thumb {
    aspect-ratio: 16 / 9;
  }
}
.card.list {
  flex-direction: row;
  align-items: center;
  gap: 14px;
  padding: 8px 14px 8px 8px;
  border-radius: 12px;
}
.card.list .art {
  width: 34px;
  height: 34px;
  border-radius: var(--r-md);
}
.card.list .thumb {
  flex: none;
  width: 64px;
  height: 48px;
  aspect-ratio: auto;
  border-radius: 8px;
}
.thumb img,
.thumb video {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: scale 0.6s var(--ease-out);
}
.play {
  position: relative;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: #fff;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(6px);
}
.cover .thumb {
  align-content: center;
  justify-items: start;
  gap: 4px;
  padding: 38px 16px 0;
  background:
    radial-gradient(120% 90% at 100% 0%, color-mix(in oklch, hsl(calc(var(--h2)) 75% 55%) 34%, transparent), transparent 60%),
    linear-gradient(140deg, color-mix(in oklch, hsl(calc(var(--h1)) 70% 52%) 30%, var(--surface-2)), color-mix(in oklch, hsl(calc(var(--h2)) 60% 45%) 14%, var(--surface)));
}
.win {
  position: absolute;
  top: 15px;
  left: 48px;
  display: flex;
  gap: 4px;
}
.win i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-4);
  opacity: 0.7;
}
.cover-title {
  position: relative;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: clamp(15px, 1.6vw, 21px);
  line-height: 1.1;
  letter-spacing: -0.02em;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
  max-width: 100%;
  margin-top: 14px;
}
.cover-file {
  position: relative;
  font-size: var(--t-xs);
  color: var(--text-3);
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.list .cover-title,
.list .win,
.list .cover-file,
.list .chips,
.list .art-note,
.list .gone-note {
  display: none;
}
.live {
  z-index: 1;
}
.art {
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 16px;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.art .emoji {
  font-size: 26px;
  line-height: 1;
}
.list .art .emoji {
  font-size: 18px;
}
.art-note,
.gone-note {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 10px;
  font-size: var(--t-sm);
  color: var(--text-3);
}
.doc .thumb,
.remoto .thumb,
.gone .thumb,
.diagrama .thumb {
  gap: 10px;
  align-content: center;
  justify-items: center;
  padding: 0 14px;
}
.diagrama-mini {
  position: absolute;
  inset: 34px 10px 10px;
  overflow: hidden;
  pointer-events: none;
}
.chips {
  position: absolute;
  top: 8px;
  right: 8px;
  display: flex;
  gap: 4px;
  z-index: 2;
}
.chip {
  height: 19px;
  padding: 0 7px;
  border-radius: var(--r-pill);
  font-size: var(--t-xs);
  font-weight: 560;
  line-height: 19px;
  color: var(--text-2);
  background: color-mix(in srgb, var(--bg) 72%, transparent);
  backdrop-filter: blur(6px);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.chip.kind {
  color: var(--accent);
}

.meta {
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 9px 12px 11px;
}
.list .meta {
  flex: 1;
  padding: 0;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
}
.name {
  font-size: var(--t-lg);
  font-weight: 580;
  letter-spacing: -0.005em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sub {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: var(--t-sm);
  color: var(--text-3);
}
.dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.sess {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.when,
.size {
  margin-left: auto;
  flex: none;
  font-size: var(--t-xs);
  color: var(--text-4);
}
.size {
  margin-left: 6px;
  min-width: 52px;
  text-align: right;
}

.del,
.pick {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 3;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: 50%;
  color: var(--text-2);
  background: color-mix(in srgb, var(--bg) 72%, transparent);
  backdrop-filter: blur(6px);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: opacity 0.2s, color 0.2s, background 0.2s, scale 0.3s var(--spring);
}
.del:hover {
  color: var(--danger);
  background: var(--danger-soft);
}
.del:active {
  scale: var(--press-scale);
}
.pick {
  color: transparent;
  pointer-events: none;
}
.pick.on {
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: none;
  animation: pop 0.35s var(--spring);
}
@keyframes pop {
  from { scale: 0.6; }
}
.card.list .del,
.card.list .pick {
  top: 50%;
  left: 16px;
  translate: 0 -50%;
  width: 26px;
  height: 26px;
}
.card.list:not(.picking) .meta {
  padding-right: 34px;
}
.card.list.picking .thumb {
  margin-left: 30px;
}
.card.list .del {
  left: auto;
  right: 12px;
}
.card.picking.checked {
  box-shadow: inset 0 0 0 2px var(--accent);
}
.card.picking.checked .thumb {
  opacity: 0.85;
}
.card.leaving {
  opacity: 0;
  scale: 0.86;
  filter: blur(3px);
  pointer-events: none;
  transition: opacity 0.26s var(--ease-out), scale 0.3s var(--ease-out), filter 0.3s;
}
:root[data-motion='soft'] .card.leaving {
  scale: none;
  filter: none;
}
</style>
