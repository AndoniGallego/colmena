<script setup lang="ts">
import { computed } from 'vue'
import { PIPE_LABEL, type PipeEstado } from '../api/mrsApi'

const props = defineProps<{ estado: PipeEstado; label?: string; compact?: boolean }>()
const texto = computed(() => props.label ?? { ok: 'Verde', fallo: 'Falló', corriendo: 'Corriendo', cancelado: 'Cancelado', manual: 'Manual', sin: 'Sin pipeline' }[props.estado])
</script>

<template>
  <span class="pipe" :class="[estado, { compact }]" :title="PIPE_LABEL[estado]">
    <i class="dot" aria-hidden="true" />
    <span v-if="!compact">{{ texto }}</span>
    <span v-else class="sr">{{ PIPE_LABEL[estado] }}</span>
  </span>
</template>

<style scoped>
.pipe { --c: var(--text-4); --bgc: var(--surface-2); display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 9px 0 7px; border-radius: var(--r-pill); font-size: var(--t-sm); font-weight: 620; white-space: nowrap; color: var(--c); background: var(--bgc); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 28%, transparent); }
.pipe.compact { height: 18px; padding: 0 6px; gap: 0; }
.ok { --c: var(--st-done); --bgc: var(--st-done-soft); }
.fallo { --c: var(--danger); --bgc: var(--danger-soft); }
.corriendo { --c: var(--st-working); --bgc: var(--st-working-soft); }
.manual { --c: var(--st-blocked); --bgc: var(--st-blocked-soft); }
.dot { position: relative; width: 7px; height: 7px; border-radius: 50%; background: var(--c); }
.corriendo .dot::after { content: ''; position: absolute; inset: -3px; border-radius: 50%; border: 1.5px solid var(--c); border-right-color: transparent; animation: spin 0.9s linear infinite; }
.fallo .dot::after { content: ''; position: absolute; inset: 0; border-radius: 50%; background: var(--c); pointer-events: none; animation: beat 1.8s ease-in-out infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes beat { 0%, 100% { transform: scale(1); opacity: 0.5; } 50% { transform: scale(2.1429); opacity: 0; } }
.sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); }
:root[data-motion='soft'] .dot, :root[data-motion='soft'] .dot::after { animation: none; }
@media (prefers-reduced-motion: reduce) { .dot, .dot::after { animation: none; } }
</style>
