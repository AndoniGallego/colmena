<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { renderMarkdown } from '../lib/markdown'
import { createStreamingMarkdownThrottle } from '../lib/streamingMarkdown'
import type { Diagrama } from '../lib/diagrama'
import type { Segment } from '../lib/segments'
import DiagramaCard from './DiagramaCard.vue'
import EstadoCard from './EstadoCard.vue'
import PruebasCard from './PruebasCard.vue'
import ComandoCard from './ComandoCard.vue'

const props = defineProps<{
  segments: Segment[]
  /** text of the user message that came after this one, if any */
  answer?: string | null
  disabled?: boolean
  quiet?: boolean
  streaming?: boolean
  /** library item of each diagrama block, in order */
  diagramaLibIds?: (string | null)[]
  /** ruta de captura -> id de la Biblioteca, para la evidencia de los bloques pruebas */
  evidencias?: Record<string, string>
  /** Para los bloques comando: sesión, id del mensaje y posición del primero de este ítem en ese mensaje. */
  sessionId?: string
  cmid?: string
  cstart?: number
  ccwd?: string
}>()
defineEmits<{ pick: [text: string]; other: [] }>()

const CARET = '<span class="caret" aria-hidden="true"></span>'
function withCaret(html: string) {
  if (!html) return CARET
  const m = /(<\/(?:p|li|td|th|h[1-6]|code|blockquote)>)(\s*(?:<\/[a-z0-9]+>\s*)*)$/i.exec(html)
  return m ? html.slice(0, m.index) + CARET + html.slice(m.index) : html + CARET
}

const lastIdx = computed(() => props.segments.length - 1)
const streamMdHtml = ref('')
const throttle = createStreamingMarkdownThrottle((text) => {
  streamMdHtml.value = renderMarkdown(text)
})

const lastStreamText = computed(() => {
  if (!props.streaming) return null
  const last = props.segments[lastIdx.value]
  return last?.type === 'md' ? last.text : null
})

watch(
  lastStreamText,
  (text) => {
    if (text === null) {
      throttle.finish()
      streamMdHtml.value = ''
      return
    }
    throttle.update(text)
  },
  { immediate: true },
)

watch(
  () => props.streaming,
  (on) => {
    if (!on) throttle.finish()
  },
)

onBeforeUnmount(() => throttle.finish())

const items = computed(() => {
  let fk = -1
  let ck = -1
  return props.segments.map((s, i) => {
    const d: Diagrama | null = s.type === 'diagrama' ? s.data : null
    let html = ''
    if (s.type === 'md') {
      const live = props.streaming && i === lastIdx.value
      html = live ? streamMdHtml.value : renderMarkdown(s.text)
      html = live ? withCaret(html) : html
    }
    const cIdx = s.type === 'comando' ? (props.cstart ?? 0) + ++ck : 0
    return { s, d, libId: d ? (props.diagramaLibIds?.[++fk] ?? null) : null, html, cIdx }
  })
})
</script>

<template>
  <div class="segs">
    <template v-for="(x, i) in items" :key="i">
      <div v-if="x.s.type === 'md'" class="md seg" v-html="x.html" />
      <DiagramaCard v-else-if="x.d" class="seg" :diagrama="x.d" :lib-id="x.libId" :quiet="quiet" />
      <pre v-else-if="x.s.type === 'pregunta' || x.s.type === 'aviso'" class="md seg"><code>{{ JSON.stringify(x.s.data) }}</code></pre>
      <EstadoCard v-else-if="x.s.type === 'estado'" class="seg" :data="x.s.data" />
      <PruebasCard v-else-if="x.s.type === 'pruebas'" class="seg" :data="x.s.data" :evidencias="evidencias" />
      <ComandoCard v-else-if="x.s.type === 'comando'" class="seg" :data="x.s.data" :session-id="sessionId" :mid="cmid" :indice="x.cIdx" :cwd="ccwd" />
      <div v-else-if="x.s.type === 'pending'" class="seg tr-pending mono"><span class="spin" /> Armando {{ x.s.kind === 'diagrama' ? 'el diagrama' : x.s.kind === 'pregunta' ? 'la pregunta' : x.s.kind === 'aviso' ? 'el aviso' : x.s.kind === 'estado' ? 'el estado' : x.s.kind === 'pruebas' ? 'el informe de pruebas' : x.s.kind === 'comando' ? 'el comando' : 'las preguntas' }}…</div>
    </template>
  </div>
</template>

<style scoped>
.segs {
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.seg + .seg {
  margin-top: 0.7em;
}
.segs :deep(.caret) {
  display: inline-block;
  width: 0.5em;
  height: 1.05em;
  margin-left: 2px;
  vertical-align: -0.17em;
  border-radius: 2px;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent), 0 0 2px var(--accent);
  animation: caret 0.9s var(--ease-in-out) infinite;
}
@keyframes caret {
  50% { opacity: 0.25; transform: scaleY(0.82); box-shadow: 0 0 2px var(--accent); }
}
.tr-pending {
  align-self: flex-start;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 12px;
  border-radius: var(--r-md);
  border: 1px dashed var(--accent-line);
  color: var(--accent);
  font-size: 12px;
  letter-spacing: 0.04em;
}
.spin {
  flex: none;
  width: 11px;
  height: 11px;
  border-radius: 50%;
  border: 1.5px solid var(--accent);
  border-right-color: transparent;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
:root[data-motion='soft'] .segs :deep(.caret) {
  animation: none;
}
</style>
