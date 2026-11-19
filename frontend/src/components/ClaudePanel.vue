<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { claudeUso, claudeUsoError, refreshClaudeUso } from '../state/app'
import { fmtTokens } from '../lib/tokens'
import { AGRUPAR, AGRUPAR_LABEL, RANGOS, RANGO_LABEL, itemsDesglose, reinicioLabel, type UsoAgrupar, type UsoRango } from '../lib/usoClaude'
import { gsap, isSoft, useGsap } from '../motion'
import SegControl from './SegControl.vue'
import DesgloseBar from './DesgloseBar.vue'
import HistorialBars from './HistorialBars.vue'
import LimiteRing from './LimiteRing.vue'

const { run } = useGsap()
const data = computed(() => claudeUso.value)
const rango = ref<UsoRango>('hoy')
const agrupar = ref<UsoAgrupar>('sesiones')
const AGRUPAR_OPTS = AGRUPAR.map((a) => ({ value: a, label: AGRUPAR_LABEL[a] }))
const RANGO_SUFIJO: Record<UsoRango, string> = { hoy: 'hoy', '7d': 'en los últimos 7 días', '30d': 'en los últimos 30 días' }

const items = computed(() => {
  if (!data.value) return []
  return itemsDesglose(data.value.desglose[rango.value][agrupar.value])
})
const limites = computed(() => {
  const l = data.value?.limites
  if (!l) return []
  const now = new Date()
  return [
    l.fiveHour && { key: '5h', titulo: 'Últimas 5 horas', lim: l.fiveHour, reinicio: reinicioLabel(l.fiveHour, now) },
    l.sevenDay && { key: '7d', titulo: 'Semana', lim: l.sevenDay, reinicio: reinicioLabel(l.sevenDay, now) },
  ].filter((x): x is NonNullable<typeof x> => !!x)
})

const nums = reactive<Record<UsoRango, number>>({ hoy: 0, '7d': 0, '30d': 0 })
function tween(first: boolean) {
  if (!data.value) return
  const to = { hoy: data.value.totales.hoy.total, '7d': data.value.totales['7d'].total, '30d': data.value.totales['30d'].total }
  if (isSoft()) return Object.assign(nums, to)
  run(() => gsap.to(nums, { ...to, duration: first ? 1.3 : 0.8, delay: first ? 0.2 : 0, ease: 'expo.out', overwrite: true }))
}
let first = true
watch(data, () => {
  tween(first)
  first = false
}, { immediate: true })

onMounted(() => {
  void refreshClaudeUso()
})
</script>

<template>
  <div class="cp">
    <template v-if="data">
      <article v-if="limites.length" class="card lim">
        <header class="c-head"><h3>Límites del plan</h3></header>
        <div class="lim-grid" :data-n="limites.length">
          <LimiteRing v-for="(l, i) in limites" :key="l.key" :pct="l.lim.pct" :titulo="l.titulo" :reinicio="l.reinicio" :vencido="l.lim.vencido" :delay="i * 0.12" />
        </div>
      </article>

      <article class="card tot" :class="{ solo: !limites.length }">
        <header class="c-head"><h3>Tokens usados</h3></header>
        <div class="tiles" role="radiogroup" aria-label="Período">
          <button
            v-for="r in RANGOS"
            :key="r"
            class="tile"
            :class="{ on: rango === r }"
            role="radio"
            :aria-checked="rango === r"
            @click="rango = r"
          >
            <span class="t-lbl">{{ RANGO_LABEL[r] }}</span>
            <b class="t-num mono">{{ fmtTokens(nums[r]) }}</b>
            <span class="t-sub">{{ data.totales[r].mensajes }} {{ data.totales[r].mensajes === 1 ? 'mensaje' : 'mensajes' }}</span>
          </button>
        </div>
        <DesgloseBar :tokens="data.totales[rango]" :label="`Tipos de token ${RANGO_SUFIJO[rango]}`" />
      </article>

      <article class="card hist">
        <header class="c-head"><h3>Últimos días</h3></header>
        <HistorialBars :dias="data.historial" :tope="0" />
      </article>

      <article class="card des">
        <header class="c-head">
          <h3>Quién gastó {{ RANGO_SUFIJO[rango] }}</h3>
        </header>
        <SegControl v-model="agrupar" :options="AGRUPAR_OPTS" label="Agrupar por" class="ag" />
        <DesgloseBar v-if="items.length" :key="`${rango}-${agrupar}`" :items="items" :label="`Uso por ${AGRUPAR_LABEL[agrupar].toLowerCase()} ${RANGO_SUFIJO[rango]}`" />
        <p v-else class="hint">Sin uso {{ RANGO_SUFIJO[rango] }}.</p>
      </article>
    </template>
    <article v-else class="card full"><p class="hint">{{ claudeUsoError ? 'No pude leer el uso de tus sesiones.' : 'Leyendo tus sesiones… la primera vez tarda unos segundos.' }}</p></article>

  </div>
</template>

<style scoped>
.cp { display: grid; gap: 14px; min-width: 0; }
.card { min-width: 0; padding: 18px; border-radius: 16px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
.c-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 14px; }
.c-head h3 { margin: 0; font-size: 13px; font-weight: 600; letter-spacing: 0.02em; color: var(--text-2); }
.hint { margin: 10px 0 0; font-size: 12px; line-height: 1.45; color: var(--text-4); }
.card > .hint:only-child { margin: 0; }

.lim-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.lim-grid[data-n='1'] { grid-template-columns: minmax(0, 1fr); }

.tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 18px; }
.tile {
  min-width: 0;
  display: grid;
  gap: 3px;
  padding: 12px 10px;
  border-radius: var(--r-lg);
  text-align: left;
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: background 0.25s, box-shadow 0.25s, scale 0.3s var(--spring);
}
.tile:hover { background: var(--surface-hover); }
.tile:active { scale: var(--press-scale); }
.tile.on { background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.t-lbl { font-size: var(--t-sm); font-weight: 560; color: var(--text-3); }
.tile.on .t-lbl { color: var(--accent); }
.t-num { font-family: var(--font-display); font-size: clamp(19px, 5.6vw, 26px); font-weight: 650; letter-spacing: -0.025em; line-height: 1.1; color: var(--text); font-variant-numeric: tabular-nums; white-space: nowrap; }
.t-sub { font-size: 11px; color: var(--text-4); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.ag { margin-bottom: 16px; }

@media (min-width: 1024px) {
  .cp { grid-template-columns: minmax(0, 5fr) minmax(0, 7fr); gap: 16px; }
  .card { padding: 22px; }
  .tot.solo, .hist, .des, .full { grid-column: 1 / -1; }
  .lim { display: grid; align-content: start; }
  .lim-grid { align-items: start; }
  .tile { padding: 14px 14px; }
  .t-num { font-size: 26px; }
  .ag { max-width: 360px; }
}
</style>
