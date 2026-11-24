<script setup lang="ts">
import { computed } from 'vue'
import type { AgentDisplayStatus } from '../api/types'
import Icon from './Icon.vue'

const props = defineProps<{ status: AgentDisplayStatus; small?: boolean; label?: string }>()
const LABEL: Record<AgentDisplayStatus, string> = {
  idle: 'En espera',
  working: 'Trabajando',
  fondo: 'En segundo plano',
  blocked: 'Bloqueado',
  done: 'Terminado',
  unknown: 'Sin agente',
}
const text = computed(() => props.label ?? LABEL[props.status])
</script>

<template>
  <span class="pill" :class="{ small }" :data-st="status">
    <span class="glyph">
      <Icon v-if="status === 'blocked'" name="warn" :size="small ? 11 : 12" />
      <Icon v-else-if="status === 'done'" name="check" :size="small ? 11 : 12" />
      <i v-else class="dot" />
    </span>
    <Transition name="lbl" mode="out-in">
      <span :key="text" class="text">{{ text }}</span>
    </Transition>
  </span>
</template>

<style scoped>
.pill {
  --c: var(--st-idle);
  --bg: var(--st-idle-soft);
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 9px 0 7px;
  border-radius: var(--r-pill);
  color: var(--c);
  background: var(--bg);
  font-size: var(--t-sm);
  font-weight: 560;
  letter-spacing: 0.01em;
  white-space: nowrap;
  overflow: hidden;
  position: relative;
  transition: color 0.5s var(--ease-out), background-color 0.5s var(--ease-out);
}
.pill.small {
  height: 19px;
  font-size: 11px;
  padding: 0 7px 0 6px;
  gap: 5px;
}
.pill[data-st='working'] { --c: var(--st-working); --bg: var(--st-working-soft); }
.pill[data-st='fondo'] { --c: var(--st-fondo); --bg: var(--st-fondo-soft); }
.pill[data-st='blocked'] { --c: var(--st-blocked); --bg: var(--st-blocked-soft); }
.pill[data-st='done'] { --c: var(--st-done); --bg: var(--st-done-soft); }
.pill[data-st='unknown'] { --c: var(--st-unknown); --bg: transparent; box-shadow: inset 0 0 0 1px var(--line-2); }

.glyph {
  display: grid;
  place-items: center;
  width: 12px;
}
.dot {
  position: relative;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.dot::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.5;
  pointer-events: none;
}
.pill[data-st='working'] .dot {
  animation: breathe 1.6s var(--ease-in-out) infinite;
}
.pill[data-st='working'] .dot::after {
  animation: breathe-halo 1.6s var(--ease-in-out) infinite;
}
.pill[data-st='fondo'] .dot {
  animation: breathe 2.8s var(--ease-in-out) infinite;
}
.pill[data-st='fondo'] .dot::after {
  animation: breathe-halo 2.8s var(--ease-in-out) infinite;
}
.pill[data-st='blocked'] .glyph {
  animation: nudge 4.2s var(--ease-in-out) infinite;
  transform-origin: 50% 80%;
}
@keyframes nudge {
  0%, 82%, 100% { transform: rotate(0); }
  86% { transform: rotate(-14deg); }
  90% { transform: rotate(11deg); }
  94% { transform: rotate(-6deg); }
}
:root[data-motion='soft'] .pill .glyph,
:root[data-motion='soft'] .pill::after {
  animation: none;
}
@keyframes breathe {
  0%, 100% { transform: scale(1); }
  50% { transform: scale(0.8); }
}
@keyframes breathe-halo {
  0%, 100% { transform: scale(1); opacity: 0.5; }
  50% { transform: scale(2.3333); opacity: 0; }
}
.lbl-enter-active { transition: transform 0.35s var(--ease-out), opacity 0.25s; }
.lbl-leave-active { transition: transform 0.18s ease-in, opacity 0.15s; }
.lbl-enter-from { transform: translateY(8px); opacity: 0; }
.lbl-leave-to { transform: translateY(-8px); opacity: 0; }
</style>
