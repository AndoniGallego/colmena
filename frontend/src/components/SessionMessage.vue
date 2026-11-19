<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { splitAttachments } from '../lib/attachments'
import { bashLocal } from '../lib/bashLocal'
import { libIdsPorDiagrama } from '../lib/biblioteca'
import { parseSegments } from '../lib/segments'
import { cachedLibItem } from '../state/biblioteca'
import { crearNota, notas } from '../state/notas'
import { notaDeMensaje, recortarNota } from '../lib/notas'
import { destinoVisible, guardarEnNotas } from '../lib/notasMovimiento'
import { clock } from '../lib/time'
import type { IndexedItem } from '../lib/transcript'
import { cascadeDelay, gsap, isSoft, useGsap } from '../motion'
import AttachThumbs from './AttachThumbs.vue'
import Icon from './Icon.vue'
import LibChips from './LibChips.vue'
import SegmentsView from './SegmentsView.vue'

const props = defineProps<{
  item: IndexedItem
  quiet?: boolean
  answer?: string | null
  locked?: boolean
  /** Sesión dueña del mensaje: habilita Correr en los bloques comando. */
  sessionId?: string
  sessionNombre?: string
}>()
const emit = defineEmits<{ pick: [text: string]; other: [] }>()

const bash = computed(() => (props.item.kind === 'user' ? bashLocal(props.item.text) : null))
const user = computed(() => (props.item.kind === 'user' && !bash.value ? splitAttachments(props.item.text) : null))
const segments = computed(() => (props.item.kind === 'claude' ? parseSegments(props.item.text) : []))
const diagramaLibIds = ref<(string | null)[]>([])
const titulosDiagrama = computed(() => segments.value.flatMap((s) => (s.type === 'diagrama' ? [s.data.titulo] : [])))
watch(
  () => [titulosDiagrama.value.join('\n'), props.item.lib_ids?.join()],
  async () => {
    if (!titulosDiagrama.value.length || !props.item.lib_ids?.length) {
      diagramaLibIds.value = []
      return
    }
    const got = await Promise.all(props.item.lib_ids.map(cachedLibItem))
    diagramaLibIds.value = libIdsPorDiagrama(titulosDiagrama.value, got.filter((i) => !!i))
  },
  { immediate: true },
)
const when = computed(() => {
  const t = Date.parse(props.item.ts)
  return Number.isNaN(t) ? '' : clock(t)
})

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const textoEl = ref<HTMLElement | null>(null)
const marcaEl = ref<HTMLElement | null>(null)

/** Lo que se ve como texto del mensaje: la prosa de Claude (sin bloques estado/opciones/pruebas) o el texto del usuario sin adjuntos. */
const textoVisible = computed(() => {
  if (user.value) return user.value.text.trim()
  return segments.value
    .flatMap((s) => (s.type === 'md' ? [s.text.trim()] : []))
    .filter(Boolean)
    .join('\n\n')
})
const puedeGuardar = computed(() => !!props.sessionId && !bash.value && (props.item.kind === 'user' || props.item.kind === 'claude') && !!textoVisible.value)
const tieneNota = computed(() => !!props.sessionId && !!notaDeMensaje(notas.value, props.sessionId, props.item.ts))
const errorNota = ref('')
const avisoNota = ref('')
const guardando = ref(false)
let errorTimer: ReturnType<typeof setTimeout> | undefined

function textoAGuardar(): string {
  const sel = window.getSelection()
  const el = textoEl.value
  if (sel && el && !sel.isCollapsed && sel.rangeCount && el.contains(sel.anchorNode) && el.contains(sel.focusNode)) {
    const t = sel.toString().trim()
    if (t) return t
  }
  return textoVisible.value
}

async function guardarNota() {
  if (!props.sessionId || guardando.value || tieneNota.value) return
  guardando.value = true
  errorNota.value = ''
  avisoNota.value = ''
  clearTimeout(errorTimer)
  const { texto, recortado } = recortarNota(textoAGuardar())
  try {
    await crearNota({ tipo: 'apunte', texto, origen: { sid: props.sessionId, nombre: props.sessionNombre ?? '', ts: props.item.ts } })
  } catch {
    errorNota.value = 'No pude guardar la nota. Probá de nuevo.'
    errorTimer = setTimeout(() => (errorNota.value = ''), 4000)
    guardando.value = false
    return
  }
  guardando.value = false
  if (recortado) {
    avisoNota.value = 'Guardé la nota recortada: era muy larga.'
    errorTimer = setTimeout(() => (avisoNota.value = ''), 4000)
  }
  const origen = textoEl.value
  const destinos = [...document.querySelectorAll('[data-notas-destino]')]
  await nextTick()
  if (!origen) return
  try {
    await guardarEnNotas(origen, destinos.find((d) => destinoVisible(d)) ?? null, marcaEl.value)
  } catch {
    // La animación es adorno: la nota ya quedó guardada.
  }
}

onBeforeUnmount(() => clearTimeout(errorTimer))

onMounted(() => {
  const el = root.value
  if (!el || props.quiet) return
  if (isSoft()) {
    run(() => gsap.from(el, { opacity: 0, duration: 0.25 }))
    return
  }
  const q = gsap.utils.selector(el)
  const delay = cascadeDelay(0.05, 8)
  run(() => {
    if (props.item.kind === 'user') {
      gsap.from(q('.bubble'), { y: 18, scale: 0.9, opacity: 0, transformOrigin: '100% 100%', duration: 0.65, ease: 'back.out(1.8)', delay })
    } else {
      gsap
        .timeline({ delay })
        .from(q('.rail'), { scale: 0, opacity: 0, duration: 0.6, ease: 'elastic.out(1.2, 0.45)', transformOrigin: '7px 4px' })
        .from(q('.content'), { y: 10, opacity: 0, duration: 0.55, ease: 'power3.out' }, 0.05)
    }
  })
})
</script>

<template>
  <article ref="root" class="msg" :data-role="item.kind" :data-ts="item.ts || undefined">
    <template v-if="bash">
      <div class="bash" :data-tipo="bash.tipo">
        <p v-if="bash.tipo === 'comando'" class="linea mono"><span class="prompt" aria-hidden="true">$</span> <code>{{ bash.texto }}</code></p>
        <template v-else>
          <pre v-if="bash.texto" class="salida mono">{{ bash.texto }}</pre>
          <pre v-if="bash.error" class="error mono">{{ bash.error }}</pre>
          <p v-if="!bash.texto && !bash.error" class="vacia">Sin salida</p>
        </template>
      </div>
      <span v-if="when && bash.tipo === 'salida'" class="when mono">{{ when }}</span>
    </template>
    <template v-else-if="user">
      <div ref="textoEl" class="bubble">
        <AttachThumbs v-if="user.ids.length || user.images" :ids="user.ids" :images="user.images" :solo="!user.text" />
        <p v-if="user.text" class="text">{{ user.text }}</p>
      </div>
      <div class="pie">
        <span v-if="when" class="when mono">{{ when }}</span>
        <span v-if="tieneNota" ref="marcaEl" class="marca-nota mono">NOTA</span>
        <button
          v-if="puedeGuardar"
          class="guardar hit"
          type="button"
          data-guardar-nota
          :aria-label="tieneNota ? 'Ya está en notas' : 'Guardar como nota'"
          :title="tieneNota ? 'Ya está en notas' : 'Guardar como nota'"
          :disabled="guardando || tieneNota"
          @click="guardarNota"
        >
          <Icon name="hex" :size="13" />
        </button>
      </div>
      <p v-if="errorNota" class="nota-error" role="alert">{{ errorNota }}</p>
      <p v-if="avisoNota" class="nota-aviso" role="status">{{ avisoNota }}</p>
    </template>
    <template v-else>
      <div class="rail" aria-hidden="true" />
      <div ref="textoEl" class="content">
        <SegmentsView
          :segments="segments"
          :diagrama-lib-ids="diagramaLibIds"
          :evidencias="item.evidencias"
          :session-id="sessionId"
          :cmid="item.cmid"
          :cstart="item.cstart"
          :ccwd="item.ccwd"
          :answer="answer"
          :disabled="locked"
          :quiet="quiet"
          @pick="emit('pick', $event)"
          @other="emit('other')"
        />
        <LibChips v-if="item.lib_ids?.length" :ids="item.lib_ids" library />
        <div class="pie">
          <span v-if="when" class="when mono">{{ when }}</span>
          <span v-if="tieneNota" ref="marcaEl" class="marca-nota mono">NOTA</span>
          <button
          v-if="puedeGuardar"
          class="guardar hit"
          type="button"
          data-guardar-nota
          :aria-label="tieneNota ? 'Ya está en notas' : 'Guardar como nota'"
          :title="tieneNota ? 'Ya está en notas' : 'Guardar como nota'"
          :disabled="guardando || tieneNota"
          @click="guardarNota"
        >
            <Icon name="hex" :size="13" />
          </button>
        </div>
        <p v-if="errorNota" class="nota-error" role="alert">{{ errorNota }}</p>
      <p v-if="avisoNota" class="nota-aviso" role="status">{{ avisoNota }}</p>
      </div>
    </template>
  </article>
</template>

<style scoped>
.msg[data-role='user']:has(> .bash) {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  margin: 2px 0;
}
.msg[data-role='user']:has(> .bash[data-tipo='comando']) {
  margin-top: 20px;
}
.bash {
  width: min(78%, 560px);
  padding: 8px 12px;
  background: var(--surface-1, var(--surface-2));
  border: 1px solid var(--line-2);
  font-size: var(--t-md);
  line-height: 1.5;
}
.bash[data-tipo='comando'] {
  border-radius: 10px 10px 0 0;
  border-bottom-style: dashed;
}
.bash[data-tipo='salida'] {
  border-radius: 0 0 4px 10px;
  border-top: 0;
  max-height: 320px;
  overflow: auto;
}
.bash .linea,
.bash pre,
.bash .vacia {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.bash .prompt {
  color: var(--accent, var(--text-3));
  user-select: none;
}
.bash .salida {
  color: var(--text-2);
}
.bash .error {
  color: var(--danger, #e66);
}
.bash .vacia {
  color: var(--text-4);
  font-style: italic;
}
.msg[data-role='user'] {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 3px;
  margin: 20px 0 12px;
}
.bubble {
  max-width: min(78%, 560px);
  padding: 9px 14px;
  border-radius: 14px 14px 4px 14px;
  background: var(--surface-2);
  border: 1px solid var(--line-2);
  overflow-wrap: anywhere;
  font-size: 14.5px;
  line-height: 1.5;
}
.text {
  margin: 0;
  white-space: pre-wrap;
}
.when {
  font-size: var(--t-xs);
  color: var(--text-4);
  letter-spacing: 0.03em;
}

.msg[data-role='claude'] {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr);
  gap: 12px;
  margin: 6px 0 10px;
}
.rail {
  position: relative;
  margin-top: 8px;
}
.rail::before {
  content: '';
  position: absolute;
  top: 0;
  left: 3px;
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--text-4);
}
.rail::after {
  content: '';
  position: absolute;
  top: 14px;
  bottom: 4px;
  left: 6px;
  width: 1px;
  background: linear-gradient(var(--line-2), transparent);
}
.content {
  min-width: 0;
  font-size: 14.5px;
  line-height: 1.62;
  color: var(--text);
}
.pie {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 2px;
}
.msg[data-role='user'] .pie {
  justify-content: flex-end;
}
.marca-nota {
  font-size: var(--t-xs);
  letter-spacing: 0.08em;
  color: var(--miel);
  background: var(--miel-soft);
  padding: 0 6px;
  border-radius: 6px;
}
.guardar {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  padding: 0;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-4);
  cursor: pointer;
  transition: color 0.15s, background-color 0.15s;
}
.guardar::before {
  content: '';
  position: absolute;
  inset: -10px;
}
@media (hover: hover) and (pointer: fine) {
  .guardar { opacity: 0.5; transition: color 0.15s, background-color 0.15s, opacity 0.15s; }
  .msg:hover .guardar, .guardar:focus-visible { opacity: 1; }
  .guardar:hover { color: var(--miel); background: var(--miel-soft); }
}
.nota-error {
  margin: 2px 0 0;
  font-size: var(--t-xs);
  color: var(--danger, #e66);
}
.nota-aviso {
  margin: 2px 0 0;
  font-size: var(--t-xs);
  color: var(--text-3);
}
.guardar:disabled {
  cursor: default;
  opacity: 0.5;
}
.msg.resaltado {
  animation: resaltar 1.5s ease-out;
}
@keyframes resaltar {
  0%, 60% { background: var(--miel-soft); }
  100% { background: transparent; }
}
@media (max-width: 1023px) {
  .msg[data-role='claude'] {
    grid-template-columns: 8px minmax(0, 1fr);
    gap: 10px;
  }
  .rail::before { left: 0; }
  .rail::after { left: 3px; }
  .bubble { max-width: 88%; }
}
</style>
