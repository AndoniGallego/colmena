<script setup lang="ts">
import { computed } from 'vue'
import { ApiError } from '../api/types'
import {
  CARPETA_DISTINTA,
  carpetaDistinta,
  claveComando,
  estadoComando,
  ponerEstadoComando,
  tramosComando,
  type Comando,
} from '../lib/comando'
import Icon from './Icon.vue'

const props = defineProps<{
  data: Comando
  /** Sin sesión o sin id de mensaje (vista previa, Biblioteca) la tarjeta solo muestra el comando. */
  sessionId?: string
  mid?: string
  indice?: number
  /** El cwd real de la sesión en ese mensaje (lo anota Claude Code); es donde corre el comando. */
  cwd?: string
}>()

const YA_CORRIDO = 'Ese comando ya se corrió'

const clave = computed(() => (props.sessionId && props.mid ? claveComando(props.sessionId, props.mid, props.indice ?? 0) : ''))
const estado = computed(() => (clave.value ? estadoComando(clave.value) : { fase: 'listo' as const }))
const tramos = computed(() => tramosComando(props.data.comando))
const raro = computed(() => tramos.value.some((t) => t.raro))
const invalido = computed(() => props.data.error ?? (carpetaDistinta(props.data.carpeta, props.cwd) ? CARPETA_DISTINTA : ''))
const puede = computed(() => !!clave.value && !invalido.value)
const abierta = computed(() => puede.value && (estado.value.fase === 'listo' || estado.value.fase === 'error'))

async function correr() {
  if (!abierta.value || !props.sessionId || !props.mid) return
  const k = clave.value
  ponerEstadoComando(k, { fase: 'corriendo' })
  try {
    // Import tardío: state/app toca window al cargarse y esta tarjeta también se dibuja fuera del navegador.
    const { correrComando } = await import('../state/app')
    await correrComando(props.sessionId, { mid: props.mid, indice: props.indice ?? 0, comando: props.data.comando })
    ponerEstadoComando(k, { fase: 'corrido' })
  } catch (e) {
    if (e instanceof ApiError && e.status === 409 && e.detail === YA_CORRIDO) {
      ponerEstadoComando(k, { fase: 'corrido', ya: true })
      return
    }
    const detalle = e instanceof ApiError && e.detail ? e.detail : 'No pude correrlo: revisá la conexión y probá de nuevo'
    ponerEstadoComando(k, { fase: 'error', detalle })
  }
}

function descartar() {
  if (!abierta.value) return
  ponerEstadoComando(clave.value, { fase: 'descartado' })
}

function onKey(e: KeyboardEvent) {
  if (!abierta.value) return
  if (e.key === 'Enter' && e.target === e.currentTarget) {
    e.preventDefault()
    void correr()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    descartar()
  }
}
</script>

<template>
  <article
    class="cc"
    :class="estado.fase"
    :tabindex="abierta ? 0 : undefined"
    :aria-label="`La sesión pide correr: ${data.comando}`"
    @keydown="onKey"
  >
    <header class="top">
      <span class="kicker"><Icon name="terminal" :size="13" /> Pide correr un comando</span>
      <span v-if="abierta" class="kbd mono" aria-hidden="true">Enter corre · Esc no</span>
    </header>
    <pre class="cmd mono" dir="ltr"><template v-for="(t, i) in tramos" :key="i"><mark v-if="t.raro" class="rara">{{ t.texto }}</mark><template v-else>{{ t.texto }}</template></template></pre>
    <p v-if="raro" class="aviso-raro">Tiene caracteres no comunes: revisá los resaltados antes de correrlo</p>
    <p v-if="data.motivo" class="motivo">{{ data.motivo }}</p>
    <p v-if="cwd" class="carpeta mono" :title="cwd">Corre en: {{ cwd }}</p>
    <p v-else class="carpeta mono">Corre en la carpeta de la sesión</p>
    <p v-if="invalido" class="err" role="alert">No se puede correr: {{ invalido }}</p>
    <p v-else-if="estado.fase === 'error'" class="err" role="alert">{{ estado.detalle }}</p>
    <div v-if="abierta" class="actions">
      <button type="button" class="btn primary correr" @click="correr">Correr</button>
      <button type="button" class="btn ghost no" @click="descartar">No</button>
    </div>
    <p v-else-if="estado.fase === 'corriendo'" class="fin mono" role="status"><span class="spin" /> Corriendo…</p>
    <p v-else-if="estado.fase === 'corrido'" class="fin ok mono" role="status">
      <Icon name="check" :size="13" /> {{ estado.ya ? 'Ya se corrió' : 'Corrido' }} · la salida le llega a la sesión
    </p>
    <p v-else-if="estado.fase === 'descartado'" class="fin mono" role="status">Descartado</p>
  </article>
</template>

<style scoped>
.cc {
  display: grid;
  gap: 8px;
  min-width: 0;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid var(--accent-line);
  background: var(--surface);
  outline: none;
}
.cc:focus-visible {
  box-shadow: 0 0 0 2px var(--accent);
}
.cc.descartado,
.cc.corrido {
  border-color: var(--line);
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.kicker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--t-xs);
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-3);
}
.kbd {
  display: none;
  font-size: 11px;
  color: var(--text-4);
}
@media (hover: hover) and (pointer: fine) {
  .cc:focus-within .kbd {
    display: inline;
  }
}
.cmd {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  background: var(--surface-2);
  font-family: var(--font-mono);
  font-size: var(--t-md);
  line-height: 1.45;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--text);
  direction: ltr;
  unicode-bidi: isolate;
  text-align: left;
}
.rara {
  border-radius: 3px;
  background: color-mix(in srgb, var(--st-blocked) 22%, transparent);
  color: inherit;
  outline: 1px solid var(--st-blocked);
}
.aviso-raro {
  margin: 0;
  font-size: var(--t-md);
  color: var(--st-blocked);
}
.motivo {
  margin: 0;
  font-size: var(--t-lg);
  line-height: 1.45;
  color: var(--text-2);
}
.carpeta {
  margin: 0;
  font-size: var(--t-sm);
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.err {
  margin: 0;
  font-size: var(--t-md);
  color: var(--st-blocked);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.btn {
  min-height: 36px;
  padding: 0 16px;
  border-radius: var(--r-pill);
  font-size: 13px;
  font-weight: 600;
  transition: filter 0.2s, scale 0.25s var(--spring);
}
.btn:active {
  scale: var(--press-scale);
}
.primary {
  background: var(--accent);
  color: var(--accent-ink);
}
.ghost {
  color: var(--text-2);
  border: 1px solid var(--line-2);
  background: var(--surface);
}
.fin {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  font-size: 12px;
  color: var(--text-3);
}
.fin.ok {
  color: var(--accent);
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
</style>
