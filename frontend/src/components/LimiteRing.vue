<script setup lang="ts">
import { computed, onMounted, reactive, watch } from 'vue'
import { limiteEstado } from '../lib/usoClaude'
import { gsap, isSoft, useGsap } from '../motion'

const props = defineProps<{ pct: number; titulo: string; reinicio: string; vencido?: boolean; delay?: number }>()
const { run } = useGsap()

const R = 70
const view = reactive({ p: 0 })
const estado = computed(() => (props.vencido ? 'ok' : limiteEstado(props.pct)))

function go(first: boolean) {
  const to = props.vencido ? 0 : props.pct
  if (isSoft()) {
    view.p = to
    return
  }
  run(() => gsap.to(view, { p: to, duration: first ? 1.4 : 0.9, delay: first ? 0.25 + (props.delay ?? 0) : 0, ease: 'expo.out', overwrite: true }))
}
onMounted(() => go(true))
watch(() => [props.pct, props.vencido], () => go(false))
const dash = computed(() => `${view.p.toFixed(2)} 100`)
</script>

<template>
  <div class="lr" :data-estado="estado" role="img" :aria-label="`${titulo}: ${vencido ? 'reiniciado' : `${Math.round(pct)}% usado`}, ${reinicio}`">
    <div class="ring">
      <svg viewBox="0 0 180 180" aria-hidden="true">
        <circle class="track" cx="90" cy="90" :r="R" pathLength="100" />
        <circle class="arc glow" cx="90" cy="90" :r="R" pathLength="100" :stroke-dasharray="dash" />
        <circle class="arc" cx="90" cy="90" :r="R" pathLength="100" :stroke-dasharray="dash" />
      </svg>
      <div class="mid">
        <b class="num mono">{{ vencido ? '—' : `${Math.round(view.p)}%` }}</b>
        <span class="sub">{{ vencido ? 'sin dato nuevo' : 'usado' }}</span>
      </div>
    </div>
    <div class="txt">
      <h4>{{ titulo }}</h4>
      <p>{{ reinicio }}</p>
    </div>
  </div>
</template>

<style scoped>
.lr { --c: var(--st-done); display: grid; justify-items: center; gap: 10px; min-width: 0; text-align: center; }
.lr[data-estado='aviso'] { --c: var(--st-blocked); }
.lr[data-estado='tope'] { --c: var(--danger); }
.ring { position: relative; width: 100%; max-width: 148px; aspect-ratio: 1; }
svg { display: block; width: 100%; height: 100%; rotate: -90deg; overflow: visible; }
circle { fill: none; stroke-width: 14; }
.track { stroke: color-mix(in srgb, var(--text) 8%, transparent); }
.arc { stroke: var(--c); stroke-linecap: round; transition: stroke 0.5s; }
.glow { stroke-width: 24; opacity: 0.22; filter: blur(8px); }
.mid { position: absolute; inset: 0; display: grid; place-content: center; justify-items: center; gap: 1px; }
.num { font-family: var(--font-display); font-size: clamp(24px, 7.5vw, 30px); font-weight: 650; letter-spacing: -0.03em; line-height: 1; color: var(--text); font-variant-numeric: tabular-nums; }
.sub { font-size: var(--t-sm); color: var(--text-3); }
.txt { display: grid; gap: 2px; min-width: 0; }
h4 { margin: 0; font-size: 13px; font-weight: 600; color: var(--text); }
p { margin: 0; font-size: 12px; line-height: 1.35; color: var(--text-3); }
</style>
