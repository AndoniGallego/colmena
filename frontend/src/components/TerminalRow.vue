<script setup lang="ts">
import { computed } from 'vue'
import type { Terminal } from '../api/types'
import { desktop } from '../lib/viewport'
import { terminalTitle } from '../lib/terminales'
import { openTerminal, openTerminalId } from '../state/terminales'
import { act, openAccion } from '../state/terminalActions'
import Icon from './Icon.vue'

const props = defineProps<{ terminal: Terminal }>()
const title = computed(() => terminalTitle(props.terminal))
const selected = computed(() => desktop.value && openTerminalId.value === props.terminal.pane_id)
const cerrando = computed(() => act.kind === 'cerrar' && act.paneId === props.terminal.pane_id)
</script>

<template>
  <div class="trow-wrap">
    <button type="button" class="trow" :class="{ selected }" :data-estado="terminal.estado" @click="openTerminal(terminal.pane_id)">
      <span class="ico" aria-hidden="true"><Icon name="terminal" :size="15" /></span>
      <span class="txt">
        <span class="ttl">{{ title }}</span>
        <span v-if="terminal.cwd" class="cwd mono">{{ terminal.cwd }}</span>
      </span>
      <span v-if="terminal.protegida" class="lock" title="Workspace protegido"><Icon name="lock" :size="12" /></span>
      <span class="chip mono" :class="terminal.estado"><i class="dot" />{{ terminal.estado === 'prompt' ? 'prompt' : terminal.proceso || 'corriendo' }}</span>
      <Icon class="go" name="chevron" :size="14" />
    </button>
    <button
      v-if="!terminal.protegida"
      type="button"
      class="cerrar hit"
      :class="{ on: cerrando }"
      aria-label="Cerrar terminal"
      :title="`Cerrar ${title}`"
      @click="openAccion('cerrar', terminal.pane_id)"
    >
      <Icon name="close" :size="13" />
    </button>
  </div>
</template>

<style scoped>
.trow-wrap { display: flex; align-items: center; gap: 2px; min-width: 0; max-width: 100%; }
.trow-wrap > .trow { flex: 1; }
.cerrar {
  flex: none;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--r-md);
  color: var(--text-4);
  transition: color 0.2s, background 0.2s, scale 0.3s var(--spring);
}
.cerrar:hover, .cerrar.on { color: var(--danger); background: var(--danger-soft); }
.cerrar:active { scale: var(--press-scale); }
.trow {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
  min-width: 0;
  max-width: 100%;
  min-height: 48px;
  padding: 8px 10px 8px 12px;
  border-radius: var(--r-md);
  text-align: left;
  color: var(--text);
  transition: background 0.25s var(--ease-out), box-shadow 0.25s, scale 0.35s var(--spring);
}
.trow:hover { background: var(--surface-hover); }
.trow:active { scale: 0.985; }
.trow.selected { background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.ico {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--r-md);
  color: var(--text-2);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line);
}
.txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.ttl { font-size: 14px; font-weight: 540; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cwd { font-size: 11px; color: var(--text-3); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lock { flex: none; color: var(--text-3); display: grid; }
.chip {
  flex: none;
  max-width: 110px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 9px;
  border-radius: var(--r-pill);
  font-size: 11px;
  color: var(--text-2);
  background: var(--st-idle-soft);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.chip .dot { flex: none; width: 6px; height: 6px; border-radius: 50%; background: var(--st-idle); }
.chip.corriendo { color: var(--st-working); background: var(--st-working-soft); }
.chip.corriendo .dot { background: var(--st-working); animation: tpulse 1.6s var(--ease-in-out) infinite; }
.chip.prompt .dot { background: var(--st-done); }
.go { flex: none; color: var(--text-4); transition: translate 0.3s var(--spring), color 0.2s; }
.trow:hover .go { translate: 3px 0; color: var(--text-2); }
@keyframes tpulse { 0%, 100% { opacity: 0.45; } 50% { opacity: 1; } }
:root[data-motion='soft'] .chip.corriendo .dot { animation: none; }
@media (prefers-reduced-motion: reduce) { .chip.corriendo .dot { animation: none; } }
</style>
