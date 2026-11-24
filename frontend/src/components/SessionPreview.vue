<script setup lang="ts">
import { computed, onMounted } from 'vue'
import type { Agent } from '../api/types'
import { enSegundoPlano, rotuloTarea } from '../lib/fondo'
import { digests, loadDigest } from '../state/app'
import { renderMarkdown } from '../lib/markdown'
import Icon from './Icon.vue'

const props = defineProps<{ agent: Agent }>()

const MAX_SRC = 420
const asking = computed(() => props.agent.asks_user && !!props.agent.pending)
const fondo = computed(() => enSegundoPlano(props.agent))
const fondoTxt = computed(() => (props.agent.fondo?.[0] ? rotuloTarea(props.agent.fondo[0]) : ''))
const entry = computed(() => (props.agent.session_id ? digests[props.agent.session_id] : undefined))
const lastClaude = computed(() => [...(entry.value?.data?.turns ?? [])].reverse().find((t) => t.role === 'claude')?.text ?? '')
const source = computed(() => (asking.value ? props.agent.pending : lastClaude.value || props.agent.pending || props.agent.doing))
const html = computed(() => renderMarkdown(source.value.length > MAX_SRC ? `${source.value.slice(0, MAX_SRC)}…` : source.value))
const loading = computed(() => !asking.value && !!entry.value?.loading && !entry.value.data)

onMounted(() => {
  if (!asking.value && props.agent.session_id) void loadDigest(props.agent.session_id)
})
</script>

<template>
  <div class="preview" :class="{ asking }">
    <div v-if="loading" class="skeleton" aria-label="Cargando">
      <span v-for="i in 2" :key="i" class="sk-sweep" :style="{ width: `${100 - i * 22}%`, '--sk-delay': `${i * 0.12}s` }" />
    </div>
    <template v-else-if="source">
      <span class="who mono"><Icon v-if="asking" name="warn" :size="12" />{{ asking ? 'Te pregunta' : fondo ? `En segundo plano · ${fondoTxt}` : 'Último estado' }}</span>
      <div class="md body" v-html="html" />
    </template>
    <p v-else class="empty">Todavía no escribió nada.</p>
  </div>
</template>

<style scoped>
.preview {
  min-width: 0;
}
.who {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 3px;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-4);
}
.asking .who {
  color: var(--st-blocked);
}
.body {
  min-width: 0;
  max-height: 4.5em;
  overflow: hidden;
  overflow-wrap: anywhere;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-2);
  -webkit-mask-image: linear-gradient(#000 62%, transparent);
  mask-image: linear-gradient(#000 62%, transparent);
}
.asking .body {
  color: var(--text);
}
.body > :deep(*) {
  margin: 0 0 0.3em;
}
.body :deep(.md-code) { font-size: 0.8em; max-width: 100%; }
.body :deep(.md-code code) { white-space: pre; }
.body :deep(h1), .body :deep(h2), .body :deep(h3), .body :deep(h4) { font-size: 1em; }
.skeleton {
  display: grid;
  gap: 8px;
  padding: 4px 0;
}
.skeleton span {
  height: 9px;
  border-radius: 5px;
  --sk-bg: linear-gradient(90deg, var(--surface-2), var(--surface-hover), var(--surface-2));
  --sk-left: -300%;
  --sk-w: 400%;
  --sk-dur: 1.3s;
}
.empty {
  margin: 0;
  font-size: var(--t-md);
  color: var(--text-3);
}
:root[data-motion='soft'] .skeleton span {
  animation: none;
}
</style>
