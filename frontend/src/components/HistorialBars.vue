<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { barras, diaLabel, fmtTokens } from '../lib/tokens'
import type { DiosDia } from '../api/types'
import SegControl from './SegControl.vue'

const props = defineProps<{ dias: DiosDia[]; tope: number }>()

const rango = ref<7 | 30>(7)
const RANGOS = [
  { value: 7 as const, label: '7 días' },
  { value: 30 as const, label: '30 días' },
]
const data = computed(() => barras(props.dias, rango.value, props.tope))
const sel = ref<string | null>(null)
const current = computed(() => data.value.barras.find((b) => b.fecha === sel.value) ?? data.value.barras[data.value.barras.length - 1] ?? null)
const max = computed(() => data.value.barras.reduce((m, b) => Math.max(m, b.total), 0))
const promedio = computed(() => {
  const b = data.value.barras
  return b.length ? Math.round(b.reduce((s, x) => s + x.total, 0) / b.length) : 0
})
const ready = ref(false)
onMounted(() => requestAnimationFrame(() => requestAnimationFrame(() => (ready.value = true))))
watch(rango, () => (sel.value = null))
const showLabel = (i: number, n: number) => (n <= 7 ? true : i % 5 === n % 5 || i === n - 1) && !(n > 7 && i > n - 3 && i !== n - 1)
</script>

<template>
  <div class="hb" :data-ready="ready">
    <div class="top">
      <p class="cur" aria-live="polite">
        <template v-if="current">
          <b class="mono">{{ fmtTokens(current.total) }}</b>
          <span>{{ current.fecha === dias[dias.length - 1]?.fecha ? 'hoy' : diaLabel(current.fecha) }}</span>
        </template>
      </p>
      <SegControl v-model="rango" :options="RANGOS" label="Rango del gráfico" class="rg" />
    </div>
    <div class="plot" :data-n="data.barras.length">
      <div v-if="data.topeH !== null" class="tope" :style="{ bottom: `calc(22px + ${data.topeH} * var(--area))` }"><span class="mono">tope {{ fmtTokens(tope) }}</span></div>
      <button
        v-for="(b, i) in data.barras"
        :key="b.fecha"
        class="col"
        :class="{ on: current?.fecha === b.fecha, hot: b.tope, empty: !b.total }"
        :aria-label="`${diaLabel(b.fecha)}: ${fmtTokens(b.total)} tokens`"
        :aria-pressed="current?.fecha === b.fecha"
        :style="{ '--h': `${Math.max(b.total ? 3 : 0, b.h * 100)}%`, '--d': `${i * (rango === 7 ? 0.06 : 0.02)}s` }"
        @click="sel = b.fecha"
      >
        <i class="fill" />
        <span v-if="showLabel(i, data.barras.length)" class="x">{{ rango === 7 ? b.label : b.label.split(' ')[1] }}</span>
      </button>
    </div>
    <p class="foot">Promedio <b class="mono">{{ fmtTokens(promedio) }}</b> por día · máximo <b class="mono">{{ fmtTokens(max) }}</b></p>
  </div>
</template>

<style scoped>
.hb { display: grid; gap: 14px; min-width: 0; }
.top { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.cur { margin: 0; display: flex; align-items: baseline; gap: 8px; font-size: var(--t-md); color: var(--text-3); min-height: 32px; }
.cur b { font-family: var(--font-display); font-size: 24px; font-weight: 640; letter-spacing: -0.02em; color: var(--text); }
.rg { width: 150px; flex: none; }
.plot { --area: 148px; position: relative; display: flex; align-items: stretch; gap: 6px; height: calc(var(--area) + 22px); padding-bottom: 22px; margin-top: 18px; }
.plot[data-n='30'] { gap: 2px; }
.col { position: relative; flex: 1 1 0; min-width: 0; display: flex; align-items: flex-end; border-radius: 6px; }
.col:hover { background: color-mix(in srgb, var(--text) 5%, transparent); }
.fill { display: block; width: 100%; height: 0; min-height: 0; border-radius: 6px 6px 3px 3px; background: color-mix(in srgb, var(--accent) 38%, var(--bg-2)); transition: height 0.9s var(--ease-out) var(--d), background 0.3s; }
.hb[data-ready='true'] .fill { height: var(--h); }
.col.on .fill { background: var(--accent); box-shadow: 0 0 18px -4px var(--accent); }
.col.hot .fill { background: color-mix(in srgb, var(--danger) 55%, var(--bg-2)); }
.col.hot.on .fill { background: var(--danger); box-shadow: 0 0 18px -4px var(--danger); }
.col.empty .fill { background: transparent; }
.col.empty::before { content: ''; position: absolute; left: 20%; right: 20%; bottom: 0; height: 2px; border-radius: 2px; background: var(--line-2); }
.x { position: absolute; left: 50%; bottom: -22px; translate: -50% 0; font-size: 11px; color: var(--text-4); white-space: nowrap; }
.col.on .x { color: var(--text); }
.tope { position: absolute; left: 0; right: 0; border-top: 1px dashed color-mix(in srgb, var(--danger) 60%, transparent); pointer-events: none; z-index: 2; }
.tope span { position: absolute; right: 0; top: -17px; font-size: var(--t-xs); color: var(--danger); }
.foot { margin: 0; font-size: 12px; color: var(--text-4); }
.foot b { color: var(--text-2); font-weight: 600; }
:root[data-motion='soft'] .fill { transition: height 0.2s linear; }
</style>
