<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError, type MemoriaEstado } from '../api/types'
import { borrarMemoria, getMemoriaEstado, reindexarMemoria } from '../state/app'
import { resumenIndice } from '../lib/fuentes'
import { ago, useNow } from '../lib/time'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import ConfirmSheet from './ConfirmSheet.vue'

const now = useNow()
const estado = ref<MemoriaEstado | null>(null)
const error = ref(false)
const aviso = ref<string | null>(null)
const ocupado = ref<'reindexar' | 'borrar' | null>(null)
const preguntando = ref(false)

const resumen = computed(() => (estado.value ? resumenIndice(estado.value, ago(estado.value.ultima_actualizacion, now.value)) : ''))
const engram = computed(() => {
  const e = estado.value?.engram
  if (e === 'ok') return { clase: 'ok', texto: 'Conectado', detalle: 'Las sesiones pueden buscar en tu memoria persistente, solo para leer.' }
  if (e === 'deshabilitado') return { clase: 'off', texto: 'Desactivado', detalle: 'La memoria está apagada.' }
  return { clase: 'off', texto: 'No disponible', detalle: 'El contenedor de Engram no responde; Se busca solo en las sesiones.' }
})

let refresco: ReturnType<typeof setTimeout> | undefined
async function cargar() {
  try {
    estado.value = await getMemoriaEstado()
    error.value = false
  } catch {
    error.value = true
  }
  clearTimeout(refresco)
  // Un solo vistazo extra mientras se arma el índice, sin quedarse consultando.
  if (estado.value?.actualizando) refresco = setTimeout(cargar, 6000)
}

async function reindexar() {
  if (ocupado.value) return
  ocupado.value = 'reindexar'
  aviso.value = null
  haptic(10)
  try {
    await reindexarMemoria()
    aviso.value = 'Rearmando el índice en segundo plano.'
    await cargar()
  } catch (e) {
    aviso.value = e instanceof ApiError && e.status === 429 ? 'Ya se rearmó hace poco. Probá de nuevo en unos minutos.' : e instanceof ApiError && e.status === 409 ? 'La memoria está apagada.' : 'No pude rearmar el índice.'
  } finally {
    ocupado.value = null
  }
}

async function borrar() {
  ocupado.value = 'borrar'
  try {
    await borrarMemoria()
    preguntando.value = false
    aviso.value = 'Índice borrado. Se vuelve a armar solo con las sesiones que sigan estando.'
    await cargar()
  } catch {
    aviso.value = 'No pude borrar el índice.'
    preguntando.value = false
  } finally {
    ocupado.value = null
  }
}

const { run } = useGsap()
const statusEl = ref<HTMLElement | null>(null)
watch(resumen, async (a, b) => {
  if (!b || a === b || isSoft()) return
  await nextTick()
  if (statusEl.value) run(() => gsap.from(statusEl.value, { opacity: 0, y: 4, duration: 0.35, ease: 'power3.out' }))
})

onMounted(cargar)
onBeforeUnmount(() => clearTimeout(refresco))
</script>

<template>
  <div class="card rows mem">
    <div class="row inline">
      <span class="r-txt">Memoria<small>Busca en tus sesiones de los últimos 30 días y en Engram. Se prende o apaga en la configuración del servidor.</small></span>
      <span class="switch" role="switch" :aria-checked="!!estado?.habilitada" aria-readonly="true" aria-label="Memoria" :class="{ on: estado?.habilitada }"><i /></span>
    </div>

    <div class="row">
      <span class="r-txt">
        Índice de sesiones
        <small ref="statusEl" class="estado" aria-live="polite">
          <span v-if="estado?.actualizando" class="spin" aria-hidden="true" />
          <template v-if="error">No pude leer el estado del índice.</template>
          <template v-else-if="!estado">Cargando…</template>
          <template v-else>{{ resumen }}</template>
        </small>
      </span>
      <div class="acciones">
        <button class="btn" :disabled="!!ocupado || !estado?.habilitada" @click="reindexar">
          <Icon name="refresh" :size="14" :class="{ girando: ocupado === 'reindexar' }" />
          {{ ocupado === 'reindexar' ? 'Rearmando…' : 'Reindexar' }}
        </button>
        <button class="btn danger" :disabled="!!ocupado || !estado?.indexados" @click="preguntando = true">
          <Icon name="trash" :size="14" /> Borrar índice
        </button>
      </div>
    </div>

    <div class="row inline">
      <span class="r-txt">Engram<small>{{ estado ? engram.detalle : 'Cargando…' }}</small></span>
      <span v-if="estado" class="engram" :class="engram.clase"><i aria-hidden="true" />{{ engram.texto }}</span>
    </div>

    <Transition name="aviso">
      <p v-if="aviso" class="aviso" role="status">{{ aviso }}</p>
    </Transition>
    <p class="nota"><Icon name="lock" :size="13" /> El índice vive solo en esta notebook. Se tapan secretos conocidos, pero no pegues secretos en las sesiones.</p>
  </div>

  <ConfirmSheet
    :open="preguntando"
    :busy="ocupado === 'borrar'"
    title="Borrar el índice de memoria"
    confirm-label="Borrar índice"
    busy-label="Borrando…"
    @confirm="borrar"
    @cancel="preguntando = false"
  >
    Se dejan de encontrar sesiones viejas hasta que el índice se vuelva a armar. Las sesiones y Engram no se tocan.
  </ConfirmSheet>
</template>

<style scoped>
.card { min-width: 0; border-radius: 16px; background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
.rows { padding: 4px 18px 14px; }
.row { display: flex; flex-direction: column; align-items: stretch; gap: 12px; width: 100%; padding: 16px 0; }
.row + .row { border-top: 1px solid var(--line); }
.row.inline { flex-direction: row; align-items: center; justify-content: space-between; gap: 16px; }
.r-txt { display: grid; gap: 3px; font-size: 14px; font-weight: 540; color: var(--text); min-width: 0; }
.r-txt small { font-size: 12px; font-weight: 400; line-height: 1.4; color: var(--text-4); }
.estado { display: flex; align-items: center; gap: 7px; color: var(--text-3) !important; }
.spin {
  flex: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  border: 1.5px solid var(--accent);
  border-right-color: transparent;
  animation: giro 0.8s linear infinite;
}
.girando { animation: giro 0.9s linear infinite; }
@keyframes giro { to { transform: rotate(360deg); } }
.switch {
  position: relative;
  flex: none;
  width: 42px;
  height: 24px;
  border-radius: var(--r-pill);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  opacity: 0.85;
  transition: background 0.3s;
}
.switch i {
  position: absolute;
  top: 3px;
  left: 3px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--text-4);
  transition: transform 0.4s var(--spring), background 0.3s;
}
.switch.on { background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.switch.on i { transform: translateX(18px); background: var(--accent); }
.acciones { display: flex; flex-wrap: wrap; gap: 8px; }
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  height: 38px;
  padding: 0 14px;
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 580;
  color: var(--text-2);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, scale 0.3s var(--spring), opacity 0.2s;
}
.btn:hover { background: var(--surface-hover); }
.btn:active { scale: var(--press-scale); }
.btn:disabled { opacity: 0.5; pointer-events: none; }
.btn.danger { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); box-shadow: none; }
.engram { flex: none; display: inline-flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 560; color: var(--text-3); }
.engram i { width: 8px; height: 8px; border-radius: 50%; background: var(--text-4); }
.engram.ok { color: var(--text); }
.engram.ok i { background: var(--st-done); box-shadow: 0 0 0 3px color-mix(in srgb, var(--st-done) 22%, transparent); }
.aviso { margin: 2px 0 10px; padding: 9px 12px; border-radius: var(--r-md); font-size: var(--t-md); color: var(--text-2); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.nota { display: flex; align-items: flex-start; gap: 8px; margin: 2px 0 0; padding-top: 12px; border-top: 1px solid var(--line); font-size: 12px; line-height: 1.45; color: var(--text-4); }
.nota :deep(svg) { flex: none; margin-top: 1px; }
.aviso-enter-active { transition: opacity 0.25s, transform 0.4s var(--spring); }
.aviso-leave-active { transition: opacity 0.15s; }
.aviso-enter-from { opacity: 0; transform: translateY(-4px); }
.aviso-leave-to { opacity: 0; }
:root[data-motion='soft'] .aviso-enter-from { transform: none; }
:root[data-motion='soft'] .spin,
:root[data-motion='soft'] .girando { animation-duration: 2.4s; }
@media (min-width: 1024px) {
  .row { flex-direction: row; align-items: center; justify-content: space-between; gap: 24px; }
  .acciones { flex: none; }
}
</style>
