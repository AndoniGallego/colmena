<script setup lang="ts">
import { computed } from 'vue'
import type { AgentCtx, StatusLine } from '../api/types'
import { statusParts, statusText } from '../lib/statusline'

const props = defineProps<{ line: StatusLine | null; ctx?: AgentCtx | null }>()
const parts = computed(() => statusParts(props.line, props.ctx))
const text = computed(() => (parts.value ? statusText(parts.value) : ''))
</script>

<template>
  <p v-if="parts && text" class="stat mono" :title="text" aria-label="Estado de la sesión">
    <span v-if="parts.model" class="keep">{{ parts.model }}</span>
    <template v-if="parts.ctx"><i class="sep">·</i><span class="keep ctx">{{ parts.ctx.text }}</span></template>
    <template v-if="parts.vpn"><i class="sep">·</i><span class="keep">VPN <b class="dot" :class="parts.vpn" :aria-label="parts.vpn === 'up' ? 'conectada' : 'desconectada'">●</b></span></template>
  </p>
</template>

<style scoped>
.stat {
  display: flex;
  align-items: baseline;
  gap: 7px;
  margin: 0;
  padding: 6px 18px 6px 14px;
  font-size: 11px;
  line-height: 1.3;
  color: var(--text-3);
  border-bottom: 1px solid var(--line);
  white-space: nowrap;
  min-width: 0;
}
.keep {
  flex: none;
}
.sep {
  flex: none;
  font-style: normal;
  color: var(--text-4);
}
.ctx {
  font-variant-numeric: tabular-nums;
  transition: color 0.4s;
}
.dot {
  font-weight: 400;
}
.dot.up {
  color: var(--st-done);
}
.dot.down {
  color: var(--danger);
}
</style>
