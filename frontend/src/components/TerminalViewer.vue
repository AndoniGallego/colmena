<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { findTerminal, ESTADO_LABEL, terminalTitle } from '../lib/terminales'
import { boardState } from '../state/app'
import { closeTerminal, lines, openTerminalId, stopWatching, view, watchTerminal } from '../state/terminales'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import ViewHeader from './ViewHeader.vue'
import LogoLoader from './LogoLoader.vue'
import TerminalAviso from './TerminalAviso.vue'
import TerminalActivity from './TerminalActivity.vue'
import TerminalComposer from './TerminalComposer.vue'
import TerminalOutput from './TerminalOutput.vue'
import type { TerminalMotivo } from '../api/types'
import { loadTerminalConfig, openAccion, tconfig } from '../state/terminalActions'

defineProps<{ desktop: boolean }>()

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const ref_ = computed(() => findTerminal(boardState.value.board, openTerminalId.value))
const title = computed(() => (ref_.value ? terminalTitle(ref_.value.terminal) : 'Terminal'))
const where = computed(() => (ref_.value ? [ref_.value.ws.label, ref_.value.tab.label].filter(Boolean).join(' · ') : ''))
const missing = computed(() => !!view.gone || (!ref_.value && view.loaded))
const estado = computed(() => view.estado)
const proceso = computed(() => view.proceso || ref_.value?.terminal.proceso || '')

let stop: (() => void) | null = null
watch(
  openTerminalId,
  (id) => {
    stop?.()
    stop = id ? watchTerminal(id) : null
  },
  { immediate: true },
)
onMounted(() => {
  if (!root.value || isSoft()) return
  run(() => gsap.from(root.value!.querySelectorAll('.head .vh-start > *, .head .vh-actions > *'), { y: -10, opacity: 0, duration: 0.5, ease: 'power3.out', stagger: 0.05, delay: 0.1 }))
})
onBeforeUnmount(() => {
  stop?.()
  stopWatching()
})
const canWrite = computed(() => !!tconfig.value?.escritura && !!ref_.value && !view.gone)
// Cerrar no pide la escritura prendida (como cerrar una pestaña desde el tablero); una protegida no se cierra.
const canClose = computed(() => !!ref_.value && !view.gone && !ref_.value.terminal.protegida)
const motivo = computed<TerminalMotivo | null>(() => {
  if (missing.value || !ref_.value) return null
  if (tconfig.value && !tconfig.value.escritura) return 'apagada'
  if (!tconfig.value) return null
  return view.motivo === 'apagada' ? null : view.motivo
})
const showActivity = ref(false)
watch(openTerminalId, () => (showActivity.value = false))
onMounted(() => void loadTerminalConfig())
</script>

<template>
  <section ref="root" class="tv" :class="{ desktop, writable: canWrite && !missing, conaviso: !!motivo }" aria-label="Terminal">
    <ViewHeader compact class="head thead">
      <template #back>
        <button v-if="!desktop" type="button" class="btn btn-back btn-icon" aria-label="Volver" @click="closeTerminal"><Icon name="back" :size="19" /></button>
      </template>
      <template #title>
        <div class="who">
          <h1 :title="title">{{ title }}</h1>
          <p class="where">{{ [where, view.cwd].filter(Boolean).join(' · ') }}</p>
        </div>
      </template>
      <template #actions>
        <span class="chip" :class="estado"><i class="dot" />{{ estado === 'prompt' ? 'en el prompt' : proceso || ESTADO_LABEL[estado] }}</span>
        <button v-if="desktop" type="button" class="btn btn-icon btn-ghost x" aria-label="Cerrar visor" @click="closeTerminal"><Icon name="close" :size="16" /></button>
      </template>
    </ViewHeader>

    <div v-if="(canWrite || canClose) && !missing" class="tools" role="toolbar" aria-label="Acciones de la terminal">
      <template v-if="canWrite">
        <button type="button" class="tool danger" :disabled="estado !== 'corriendo'" @click="openAccion('ctrl-c', openTerminalId!)">
          <Icon name="stop" :size="13" /><span>Ctrl+C</span>
        </button>
        <button type="button" class="tool" :disabled="estado !== 'prompt'" @click="openAccion('repetir', openTerminalId!)">
          <Icon name="refresh" :size="13" /><span>Repetir</span>
        </button>
      </template>
      <button v-if="canClose" type="button" class="tool danger cerrar hit" aria-label="Cerrar terminal" title="Cerrar terminal" @click="openAccion('cerrar', openTerminalId!)">
        <Icon name="close" :size="13" /><span class="cerrar-txt">Cerrar terminal</span>
      </button>
      <button v-if="canWrite" type="button" class="tool quiet" :aria-pressed="showActivity" @click="showActivity = !showActivity">
        <Icon name="list" :size="13" /><span>Actividad</span>
      </button>
    </div>

    <div v-if="missing" class="state">
      <p class="kicker mono">sin rastro</p>
      <h2>{{ view.gone || 'Esa terminal ya no está en el tablero' }}</h2>
      <button class="btn" @click="closeTerminal"><Icon name="back" :size="14" /> Volver</button>
    </div>
    <template v-else>
      <div v-if="!view.loaded && !view.error" class="wait"><LogoLoader /></div>
      <TerminalOutput v-else :lines="lines" :truncado="view.truncado" />
      <Transition name="rise">
        <p v-if="view.error" class="note err" role="status"><Icon name="warn" :size="14" /> {{ view.error }}. Sigo intentando.</p>
        <p v-else-if="view.paused" class="note" role="status"><Icon name="pause" :size="14" /> En pausa mientras no miras la pantalla</p>
      </Transition>
    </template>
    <Transition name="rise"><TerminalActivity v-if="showActivity" @close="showActivity = false" /></Transition>
    <TerminalAviso v-if="motivo" :motivo="motivo" :proceso="proceso" />
    <TerminalComposer v-if="canWrite && !missing" :pane-id="openTerminalId!" :prompt="estado === 'prompt'" :proceso="proceso" />
  </section>
</template>

<style scoped>
.tv { position: relative; display: flex; flex-direction: column; min-width: 0; max-width: 100%; min-height: 0; height: 100%; overflow-x: hidden; background: var(--bg); }
.thead {
  min-width: 0;
}
.desktop .thead.thead {
  padding-left: 24px;
  padding-right: 18px;
}
.x {
  flex: none;
  display: grid;
  place-items: center;
  color: var(--text-2);
  transition: background 0.2s, scale 0.35s var(--spring);
}
.x:active { scale: var(--press-scale); }
.who { flex: 1; min-width: 0; }
h1 { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: 15px; letter-spacing: -0.01em; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.where { margin: 1px 0 0; font-size: 11px; color: var(--text-4); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.chip {
  flex: none;
  max-width: 170px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
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
.chip.corriendo .dot { background: var(--st-working); }
.chip.prompt .dot { background: var(--st-done); }
.tools { display: flex; gap: 8px; padding: 8px 14px; border-bottom: 1px solid var(--line); overflow-x: auto; }
.desktop .tools { padding: 9px 24px; }
.tool {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 13px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: color 0.2s, background 0.2s, box-shadow 0.2s, opacity 0.2s, scale 0.35s var(--spring);
}
.tool:hover:not(:disabled) { color: var(--text); background: var(--accent-soft); }
.tool.danger:hover:not(:disabled) { color: var(--danger); background: var(--danger-soft); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 45%, transparent); }
.tool:active:not(:disabled) { scale: var(--press-scale); }
.tool:disabled { opacity: 0.4; cursor: not-allowed; }
/* En el celu el botón de cerrar es solo el ícono, para que la barra entre a 390px sin scroll. */
.tool.cerrar { padding: 0; width: 32px; justify-content: center; }
.cerrar-txt { display: none; }
@media (min-width: 640px) {
  .tool.cerrar { padding: 0 13px; width: auto; }
  .cerrar-txt { display: inline; }
}
.tool.quiet { margin-left: auto; box-shadow: none; color: var(--text-3); }
.tool.quiet[aria-pressed='true'] { color: var(--text); background: var(--surface-hover); }
@media (max-width: 1023px) {
  .focus span { display: none; }
  .focus { width: 34px; padding: 0; justify-content: center; }
}
.wait { flex: 1; display: grid; place-items: center; }
.state { flex: 1; display: flex; flex-direction: column; align-items: flex-start; justify-content: center; gap: 10px; padding: 24px; max-width: 520px; margin: 0 auto; }
.kicker { margin: 0; font-size: 12px; letter-spacing: 0.12em; text-transform: uppercase; color: var(--st-blocked); }
h2 { margin: 0; font-family: var(--font-display); font-weight: 600; font-size: 24px; letter-spacing: -0.02em; }
.btn { display: inline-flex; align-items: center; gap: 8px; padding: 9px 16px; border-radius: var(--r-pill); border: 1px solid var(--line-2); }
.note {
  position: absolute;
  left: 50%;
  bottom: 16px;
  translate: -50% 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  max-width: calc(100% - 32px);
  padding: 9px 16px;
  border-radius: var(--r-pill);
  font-size: 13px;
  color: var(--text);
  background: var(--surface);
  box-shadow: var(--shadow-pop);
}
.note.err { color: var(--danger); }
.writable .note { bottom: 150px; }
.conaviso .note { bottom: 130px; }
.writable.conaviso .note { bottom: 240px; }
.rise-enter-active { transition: transform 0.45s var(--spring), opacity 0.25s; }
.rise-leave-active { transition: opacity 0.2s; }
.rise-enter-from { transform: translateY(12px); opacity: 0; }
.rise-leave-to { opacity: 0; }
</style>
