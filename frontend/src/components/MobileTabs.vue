<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { mobilePageIndex, mobilePageOrder, type MobileView } from '../lib/mobileSections'
import { mrs } from '../state/mrs'
import { piezas } from '../piezas'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import NavMark from './NavMark.vue'
import Icon from './Icon.vue'
import RollingNumber from './RollingNumber.vue'

type Tab = MobileView
const props = defineProps<{ modelValue: Tab; attention: number; fresh?: number; hoyNew?: boolean; mrsPending?: number; notasPending?: number }>()
const emit = defineEmits<{ 'update:modelValue': [v: Tab] }>()
const { run } = useGsap()

const seccionesPieza = piezas().flatMap((p) => (p.seccion ? [{ id: p.id, ...p.seccion }] : []))
const order = computed(() => mobilePageOrder(mrs.habilitado, seccionesPieza))
const tabCount = computed(() => order.value.length)
const sliderStyle = computed(() => ({
  width: `calc((100% - var(--tabs-pl) - var(--tabs-pr) + 24px) / ${tabCount.value} - 8px)`,
}))

const slider = ref<HTMLElement | null>(null)
const boardBtn = ref<HTMLElement | null>(null)
const bibBtn = ref<HTMLElement | null>(null)
const piezaBtns: Record<string, HTMLElement | null> = {}
const mrsBtn = ref<HTMLElement | null>(null)
const notasBtn = ref<HTMLElement | null>(null)
const badge = ref<HTMLElement | null>(null)

function setProgress(p: number) {
  const s = slider.value
  if (!s) return
  gsap.set(s, { xPercent: p * 100, x: p * 4 })
}
defineExpose({ setProgress })

// Índice del tab: el slider se corre un ancho propio por unidad.
function tabProgress(v: Tab) {
  return mobilePageIndex(order.value, v)
}

onMounted(() => setProgress(tabProgress(props.modelValue)))

function pick(v: Tab) {
  if (v !== props.modelValue) haptic(6)
  emit('update:modelValue', v)
}

watch(
  () => props.modelValue,
  (v) => {
    const btn = ({ board: boardBtn, mrs: mrsBtn, notas: notasBtn, biblioteca: bibBtn } as Record<string, typeof boardBtn>)[v]?.value ?? piezaBtns[v]
    const icon = btn?.querySelector('svg')
    if (!icon || isSoft()) return
    run(() =>
      gsap.fromTo(icon, { scale: 0.7, rotation: v === 'board' ? -6 : 6 }, { scale: 1, rotation: 0, duration: 0.28, ease: 'power3.out' }),
    )
  },
)

watch(order, () => setProgress(tabProgress(props.modelValue)))

watch(
  () => props.attention,
  async (n, o) => {
    if (!(n > o) || !o || isSoft()) return
    await nextTick()
    if (badge.value) run(() => gsap.fromTo(badge.value, { scale: 1.45 }, { scale: 1, duration: 0.3, ease: 'power3.out' }))
  },
)
</script>

<template>
  <nav class="tabs" aria-label="Secciones" :style="{ gridTemplateColumns: `repeat(${tabCount}, minmax(0, 1fr))`, '--tab-cols': tabCount }">
    <span ref="slider" class="slider" :style="sliderStyle" aria-hidden="true" />
    <button
      ref="boardBtn"
      class="tab"
      :class="{ on: modelValue === 'board' }"
      :aria-current="modelValue === 'board' ? 'page' : undefined"
      @click="pick('board')"
    >
      <NavMark name="board" :size="18" :active="modelValue === 'board'" />
      <span>Tablero</span>
      <Transition name="badge">
        <b v-if="attention" ref="badge" class="badge warn mono"><RollingNumber :value="attention" /></b>
      </Transition>
    </button>
    <button
      v-if="mrs.habilitado"
      ref="mrsBtn"
      class="tab"
      :class="{ on: modelValue === 'mrs' }"
      :aria-current="modelValue === 'mrs' ? 'page' : undefined"
      @click="pick('mrs')"
    >
      <NavMark name="merge" :size="18" :active="modelValue === 'mrs'" />
      <span>MRs</span>
      <Transition name="badge">
        <b v-if="mrsPending" class="badge dot loop" />
      </Transition>
    </button>
    <button
      v-for="sp in seccionesPieza"
      :key="sp.id"
      :ref="(el) => (piezaBtns[sp.id] = el as HTMLElement | null)"
      class="tab"
      :class="{ on: modelValue === sp.id }"
      :aria-current="modelValue === sp.id ? 'page' : undefined"
      @click="pick(sp.id)"
    >
      <NavMark :name="sp.icono" :size="18" :active="modelValue === sp.id" />
      <span>{{ sp.titulo }}</span>
    </button>
    <button
      ref="notasBtn"
      data-notas-destino
      class="tab"
      :class="{ on: modelValue === 'notas' }"
      :aria-current="modelValue === 'notas' ? 'page' : undefined"
      :aria-label="notasPending ? `Notas, ${notasPending} para hacer` : undefined"
      @click="pick('notas')"
    >
      <Icon name="hex" :size="18" />
      <span>Notas</span>
      <Transition name="badge">
        <b v-if="notasPending" class="badge miel mono">{{ notasPending }}</b>
      </Transition>
    </button>
    <button
      ref="bibBtn"
      class="tab"
      :class="{ on: modelValue === 'biblioteca' }"
      :aria-current="modelValue === 'biblioteca' ? 'page' : undefined"
      @click="pick('biblioteca')"
    >
      <NavMark name="library" :size="18" :active="modelValue === 'biblioteca'" />
      <span>Biblioteca</span>
      <Transition name="badge">
        <b v-if="fresh" class="badge dot loop" />
      </Transition>
    </button>
  </nav>
</template>

<style scoped>
.tabs {
  position: relative;
  display: grid;
  gap: 4px;
  padding: 6px 12px;
  --tabs-pl: max(12px, env(safe-area-inset-left));
  --tabs-pr: max(12px, env(safe-area-inset-right));
  padding-left: var(--tabs-pl);
  padding-right: var(--tabs-pr);
  padding-bottom: max(8px, env(safe-area-inset-bottom));
  border-top: 1px solid var(--line);
  background: color-mix(in srgb, var(--bg) 88%, transparent);
  backdrop-filter: blur(12px);
}
.slider {
  position: absolute;
  top: 6px;
  left: var(--tabs-pl);
  width: calc(25% - 8px);
  height: 48px;
  border-radius: 12px;
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  will-change: transform;
}
.slider::after {
  content: '';
  position: absolute;
  left: 32%;
  right: 32%;
  bottom: -1px;
  height: 2px;
  border-radius: 2px;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
}
.tab {
  position: relative;
  height: 48px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  font-size: 11px;
  font-weight: 540;
  min-width: 0;
  white-space: nowrap;
  color: var(--text-3);
  transition: color 0.3s, scale 0.3s var(--spring);
}
.tab:active {
  scale: var(--press-scale);
}
.tab.on {
  color: var(--text);
}
.tab :deep(svg) {
  transition: color 0.3s;
}
.tab.on :deep(svg) {
  color: var(--accent);
}
.tab .badge { position: absolute; top: 6px; right: calc(50% - 20px); }
.badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: var(--r-md);
  font-size: 11px;
  font-weight: 600;
  display: grid;
  place-items: center;
  line-height: 18px;
}
.badge.warn {
  background: var(--st-blocked);
  color: #1a1203;
  box-shadow: 0 0 12px -2px var(--st-blocked);
}
.badge.miel {
  background: var(--miel);
  color: var(--bg);
  box-shadow: 0 0 12px -3px var(--miel);
}
.badge.dot {
  min-width: 8px;
  width: 8px;
  height: 8px;
  padding: 0;
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent);
  animation: beacon 1.8s var(--ease-in-out) infinite;
}
@keyframes beacon {
  50% { opacity: 0.55; transform: scale(0.8); }
}
.badge-enter-active { transition: transform 0.5s var(--spring), opacity 0.2s; }
.badge-leave-active { transition: transform 0.15s, opacity 0.15s; }
.badge-enter-from, .badge-leave-to { transform: scale(0.3); opacity: 0; }

/* táctil: sin vidrio (el blur de una barra fija se recalcula con cada scroll y gasta batería) */
@media (pointer: coarse) {
  .tabs {
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
    background: color-mix(in srgb, var(--bg) 94%, transparent);
  }
}
</style>
