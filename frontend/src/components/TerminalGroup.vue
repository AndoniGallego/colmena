<script setup lang="ts">
import { ref } from 'vue'
import type { Terminal } from '../api/types'
import Icon from './Icon.vue'
import TerminalRow from './TerminalRow.vue'

const props = defineProps<{ terminals: Terminal[]; collapsible: boolean }>()
const open = ref(!props.collapsible)
</script>

<template>
  <div class="tgroup">
    <button v-if="collapsible" type="button" class="thead mono" :aria-expanded="open" @click="open = !open">
      <Icon name="terminal" :size="12" />
      <span>{{ terminals.length === 1 ? '1 terminal' : `${terminals.length} terminales` }}</span>
      <Icon class="chev" :class="{ on: open }" name="chevron" :size="12" />
    </button>
    <div v-if="open" class="rows">
      <TerminalRow v-for="t in terminals" :key="t.pane_id" :terminal="t" />
    </div>
  </div>
</template>

<style scoped>
.tgroup { margin: 2px 0 6px; min-width: 0; max-width: 100%; }
.thead {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 28px;
  margin-left: 12px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  font-size: 11px;
  letter-spacing: 0.04em;
  color: var(--text-3);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: color 0.2s, background 0.2s;
}
.thead:hover { color: var(--text); background: var(--surface-hover); }
.chev { transition: rotate 0.3s var(--spring); }
.chev.on { rotate: 90deg; }
.rows { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
</style>
