<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { TranscriptFoto } from '../api/types'
import { gridLayout, overlayExtra } from '../lib/chatFotos'
import { gsap, isSoft, useGsap } from '../motion'
import { cachedLibItem, fresh } from '../state/biblioteca'
import FotoCarrusel from './FotoCarrusel.vue'

const props = defineProps<{ fotos: TranscriptFoto[]; quiet?: boolean }>()

const root = ref<HTMLElement | null>(null)
const urls = ref<Record<string, string>>({})
const open = ref<number | null>(null)
const anchor = ref<HTMLElement | null>(null)
const { run } = useGsap()

const cells = computed(() => gridLayout(props.fotos.length))
const extra = computed(() => overlayExtra(props.fotos.length))
const single = computed(() => props.fotos.length === 1)

async function preload() {
  await Promise.all(
    props.fotos.slice(0, 4).map(async (f) => {
      const item = await cachedLibItem(f.id)
      if (!item) return
      const ready = await fresh(item)
      if (ready.src) urls.value = { ...urls.value, [f.id]: ready.src }
    }),
  )
}

function openAt(i: number, el: HTMLElement) {
  anchor.value = el
  open.value = i
}

function altFor(i: number) {
  const n = props.fotos.length
  if (n === 1) return 'Captura de la sesión'
  return `Captura ${i + 1} de ${n}`
}

onMounted(() => {
  preload()
  if (!root.value || props.quiet) return
  if (isSoft()) run(() => gsap.from(root.value, { opacity: 0, duration: 0.25 }))
  else run(() => gsap.from(root.value, { opacity: 0, y: 8, duration: 0.45, ease: 'power3.out' }))
})
</script>

<template>
  <div ref="root" class="fotos" :class="{ single }" role="group" aria-label="Capturas">
    <button
      v-for="cell in cells"
      :key="cell.index"
      type="button"
      class="tile"
      :class="{ large: cell.span === 'large' }"
      :aria-label="altFor(cell.index)"
      @click="openAt(cell.index, $event.currentTarget as HTMLElement)"
    >
      <img
        v-if="urls[fotos[cell.index]?.id ?? '']"
        :src="urls[fotos[cell.index].id]"
        :alt="altFor(cell.index)"
        loading="lazy"
        decoding="async"
      />
      <span v-else class="shimmer sk-sweep" aria-hidden="true" />
      <span v-if="extra && cell.index === 3" class="more mono">+{{ extra }}</span>
    </button>
    <FotoCarrusel
      v-if="open !== null"
      :fotos="fotos"
      :start="open"
      :from="anchor"
      @close="open = null"
    />
  </div>
</template>

<style scoped>
.fotos {
  display: grid;
  gap: 3px;
  max-width: 280px;
  margin: 0.35rem 0 0.5rem;
  grid-template-columns: repeat(2, 1fr);
  border-radius: var(--r-lg);
  overflow: hidden;
}
.fotos.single {
  grid-template-columns: 1fr;
  max-width: 280px;
}
.tile {
  position: relative;
  padding: 0;
  border: 0;
  background: var(--surface);
  aspect-ratio: 1;
  overflow: hidden;
  cursor: pointer;
}
.fotos.single .tile {
  aspect-ratio: auto;
  max-height: 360px;
}
.tile.large {
  grid-row: span 2;
  aspect-ratio: auto;
}
.tile img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  outline: 1px solid var(--img-outline);
  outline-offset: -1px;
}
.fotos.single .tile img {
  height: auto;
  max-height: 360px;
  object-fit: contain;
}
.shimmer {
  display: block;
  width: 100%;
  height: 100%;
  min-height: 80px;
  --sk-bg: linear-gradient(110deg, var(--surface) 8%, color-mix(in srgb, var(--line) 40%, var(--surface)) 18%, var(--surface) 33%);
  --sk-dx: 30%;
  --sk-dur: 1.4s;
  --sk-ease: ease-in-out;
}
.more {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: color-mix(in srgb, #000 45%, transparent);
  color: #fff;
  font-size: 1.35rem;
  font-weight: 600;
}
:root[data-motion='soft'] .shimmer { opacity: 0.5; }
:root[data-motion='soft'] .shimmer::after { animation: none; }
</style>
