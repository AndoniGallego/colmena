<script setup lang="ts">
import { computed } from 'vue'
import type { CloseBlocker, ClosePane } from '../api/types'
import { blockerHint, paneLine } from '../lib/cerrar'
import { stopping, stopSession } from '../state/app'
import Icon from './Icon.vue'
import StatusPill from './StatusPill.vue'

const props = defineProps<{ panes: ClosePane[]; bloqueantes: CloseBlocker[]; actions?: boolean }>()

const blocking = computed(() => new Map(props.bloqueantes.map((b) => [b.pane_id, b.status])))
</script>

<template>
  <ul class="panes">
    <li v-for="p in panes" :key="p.pane_id" class="row" :class="{ block: blocking.has(p.pane_id) }" :data-pane="p.pane_id">
      <span class="who">
        <StatusPill v-if="p.kind && p.status" :status="p.status" small />
        <span v-else class="term"><Icon name="terminal" :size="12" /></span>
      </span>
      <span class="what">
        <span class="line"><b>{{ paneLine(p).who }}</b><template v-if="paneLine(p).what"> · {{ paneLine(p).what }}</template></span>
        <span v-if="blocking.has(p.pane_id)" class="hint">{{ blockerHint(blocking.get(p.pane_id)!) }}</span>
      </span>
      <button
        v-if="actions && blocking.get(p.pane_id) === 'working'"
        type="button"
        class="stop"
        :disabled="stopping[p.pane_id]"
        @click="stopSession(p.pane_id)"
      >
        <Icon name="stop" :size="11" /> Frenar
      </button>
    </li>
  </ul>
</template>

<style scoped>
.panes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
  padding: 8px 10px;
  border-radius: var(--r-md);
  background: var(--bg-2);
  border: 1px solid var(--line);
}
.row.block {
  border-color: color-mix(in srgb, var(--st-blocked) 55%, transparent);
  background: var(--st-blocked-soft);
}
.who {
  flex: none;
  display: inline-flex;
}
.term {
  display: inline-grid;
  place-items: center;
  height: 22px;
  min-width: 22px;
  border-radius: var(--r-pill);
  color: var(--text-3);
  background: var(--st-idle-soft);
}
.what {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}
.line {
  font-size: 13px;
  color: var(--text-2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.line b {
  font-weight: 600;
  color: var(--text);
}
.hint {
  font-size: 12px;
  color: var(--st-blocked);
}
.stop {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 11px;
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: 580;
  color: var(--text);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, scale 0.3s var(--spring);
}
.stop:hover:not(:disabled) {
  background: var(--surface-hover);
}
.stop:active:not(:disabled) {
  scale: var(--press-scale);
}
.stop:disabled {
  opacity: 0.5;
}
</style>
