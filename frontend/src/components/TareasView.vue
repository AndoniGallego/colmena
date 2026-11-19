<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { Programa } from '../api/programadasApi'
import { useFocusTrap } from '../lib/focusTrap'
import { cuandoTexto, estadoCorrida, proximaTexto } from '../lib/tareas'
import { desktop } from '../lib/viewport'
import { alternarPausa, borrar, cargarTareas, closeTareas, correr, interruptor, soltarTareas, tareas } from '../state/tareas'
import { openTerminal } from '../state/terminales'
import ConfirmSheet from './ConfirmSheet.vue'
import Icon from './Icon.vue'
import InlineAlert from './InlineAlert.vue'
import TareaForm from './TareaForm.vue'
import TrabajadoresCursor from './TrabajadoresCursor.vue'
import TerminalPinSheet from './TerminalPinSheet.vue'
import ViewFrame from './ViewFrame.vue'

const frame = ref<{ $el: HTMLElement } | null>(null)
const panel = computed(() => frame.value?.$el ?? null)
const backBtn = ref<HTMLButtonElement | null>(null)
const formAbierto = ref(false)
const editando = ref<Programa | null>(null)
const pinAbierto = ref(false)
const porBorrar = ref<Programa | null>(null)

const { onKeydown } = useFocusTrap(panel, () => !formAbierto.value && !pinAbierto.value && !porBorrar.value, { onEscape: closeTareas, initial: () => backBtn.value })

const habilitado = computed(() => tareas.data?.habilitado === true)
const programas = computed(() => tareas.data?.programas ?? [])
const cursorOk = computed(() => tareas.data?.cursor_disponible === true)
const hayCursor = computed(() => programas.value.some((p) => p.agente === 'cursor'))
const bloqueadoHasta = computed(() => (tareas.pinBloqueadoHasta > Date.now() ? tareas.pinBloqueadoHasta : null))
const ahora = computed(() => (tareas.data ? Date.now() / 1000 : 0))

function nueva() {
  editando.value = null
  formAbierto.value = true
}
function editar(p: Programa) {
  editando.value = p
  formAbierto.value = true
}
function tocarInterruptor() {
  if (habilitado.value) void interruptor(false)
  else {
    tareas.pinError = ''
    pinAbierto.value = true
  }
}
async function confirmarPin(pin: string) {
  if (await interruptor(true, pin)) pinAbierto.value = false
}
async function confirmarBorrar() {
  const p = porBorrar.value
  porBorrar.value = null
  if (p) await borrar(p)
}
function irASesion(pane: string) {
  soltarTareas()
  openTerminal(pane)
}
const hora = (t: number | null) => (t ? new Date(t * 1000).toLocaleString('es', { weekday: 'short', day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' }) : '')

function alVolver() {
  if (document.visibilityState === 'visible') void cargarTareas()
}
onMounted(() => {
  void cargarTareas()
  document.addEventListener('visibilitychange', alVolver)
})
onBeforeUnmount(() => document.removeEventListener('visibilitychange', alVolver))
</script>

<template>
  <ViewFrame
    ref="frame"
    class="tv"
    :class="{ desk: desktop }"
    role="dialog"
    aria-modal="true"
    aria-label="Tareas programadas"
    tabindex="-1"
    title="Tareas programadas"
    sticky-head
    show-back
    :back-icon="desktop ? 'close' : 'back'"
    :back-label="desktop ? 'Cerrar tareas programadas' : 'Volver'"
    @back="closeTareas"
    @keydown="onKeydown"
  >
    <template #back>
      <button ref="backBtn" type="button" class="btn btn-back btn-icon" :class="{ 'btn-back--wide': desktop }" :aria-label="desktop ? 'Cerrar tareas programadas' : 'Volver'" @click="closeTareas">
        <Icon :name="desktop ? 'close' : 'back'" :size="18" />
        <span v-if="desktop" class="esc mono">Esc</span>
      </button>
    </template>

    <div class="tv-body">
      <InlineAlert v-if="tareas.error && !tareas.data">
        {{ tareas.error }}
        <template #action>
          <button type="button" class="btn btn-ghost hit" data-test="reintentar" @click="cargarTareas">Reintentar</button>
        </template>
      </InlineAlert>
      <p v-else-if="!tareas.data" class="tv-mudo" role="status">Leyendo las tareas…</p>

      <template v-if="tareas.data">
        <section class="ui-card tv-global" data-test="global">
          <div class="tv-global-txt">
            <strong>{{ habilitado ? 'Las tareas corren solas' : 'Las tareas están apagadas' }}</strong>
            <span class="tv-mudo">{{ habilitado ? 'Corren a su hora mientras la notebook esté prendida.' : 'Ninguna corre hasta que las prendas con tu PIN.' }}</span>
          </div>
          <button type="button" class="tv-switch hit" role="switch" :aria-checked="habilitado" aria-label="Tareas programadas" :class="{ on: habilitado }" :disabled="tareas.pinBusy" data-test="interruptor" @click="tocarInterruptor"><i /></button>
        </section>
        <InlineAlert v-if="tareas.errorAccion" data-test="error-accion">{{ tareas.errorAccion }}</InlineAlert>
        <InlineAlert v-if="hayCursor && !cursorOk" data-test="sin-cursor">Cursor no está disponible: las tareas de Cursor van a salir como falladas.</InlineAlert>

        <section class="tv-sec" aria-labelledby="tv-progs">
          <div class="tv-sec-head">
            <h2 id="tv-progs" class="tv-h">Tareas</h2>
            <div class="tv-acciones">
              <button type="button" class="btn btn-ghost btn-icon hit" aria-label="Actualizar" data-test="actualizar" :disabled="tareas.cargando" @click="cargarTareas"><Icon name="refresh" :size="16" /></button>
              <button type="button" class="btn btn-primary hit" data-test="nueva" @click="nueva"><Icon name="plus" :size="14" /> Nueva</button>
            </div>
          </div>
          <p v-if="!programas.length" class="tv-mudo ui-card tv-vacio" data-test="vacio">Todavía no hay tareas programadas.</p>
          <ul v-else class="tv-lista">
            <li v-for="p in programas" :key="p.id" class="ui-card tv-prog" :class="{ pausada: p.pausada }" data-test="programa">
              <div class="tv-prog-top">
                <strong class="tv-nombre">{{ p.nombre }}</strong>
                <span class="tv-chip">{{ p.agente === 'cursor' ? 'Cursor' : 'Claude' }}</span>
              </div>
              <span class="tv-mudo tv-ruta">{{ p.repo }}</span>
              <span class="tv-mudo">{{ cuandoTexto(p.cuando) }} · <b>{{ proximaTexto(p.proxima, ahora) }}</b></span>
              <div class="tv-botones">
                <button type="button" class="btn btn-ghost hit" data-test="correr" :disabled="tareas.ocupados[p.id]" @click="correr(p)"><Icon name="play" :size="13" /> Correr ahora</button>
                <button type="button" class="btn btn-ghost hit" data-test="pausa" :disabled="tareas.ocupados[p.id]" @click="alternarPausa(p)"><Icon :name="p.pausada ? 'play' : 'pause'" :size="13" /> {{ p.pausada ? 'Reanudar' : 'Pausar' }}</button>
                <button type="button" class="btn btn-ghost hit" data-test="editar" @click="editar(p)"><Icon name="pen" :size="13" /> Editar</button>
                <button type="button" class="btn btn-ghost hit" data-test="borrar" :disabled="tareas.ocupados[p.id]" @click="porBorrar = p"><Icon name="trash" :size="13" /> Borrar</button>
              </div>
            </li>
          </ul>
        </section>

        <section class="tv-sec" aria-labelledby="tv-hist">
          <h2 id="tv-hist" class="tv-h">Últimas corridas</h2>
          <p v-if="!tareas.historial.length" class="tv-mudo ui-card tv-vacio" data-test="historial-vacio">Todavía no corrió ninguna.</p>
          <ul v-else class="tv-lista ui-card tv-hist">
            <li v-for="c in tareas.historial" :key="c.id" class="tv-corrida" data-test="corrida">
              <span class="tv-estado" :class="c.estado" :title="estadoCorrida(c.estado).etiqueta"><Icon :name="estadoCorrida(c.estado).icono" :size="14" /></span>
              <span class="tv-corrida-txt">
                <strong>{{ c.nombre }}</strong>
                <span class="tv-mudo">{{ estadoCorrida(c.estado).etiqueta }} · {{ hora(c.inicio ?? c.previsto) }}{{ c.manual ? ' · a mano' : '' }}</span>
                <span v-if="c.motivo" class="tv-mudo">{{ c.motivo }}</span>
              </span>
              <button v-if="c.pane_id" type="button" class="btn btn-ghost hit" data-test="sesion" @click="irASesion(c.pane_id)">Ver sesión</button>
            </li>
          </ul>
        </section>

        <section v-if="cursorOk || hayCursor" class="tv-sec" aria-labelledby="tv-trab">
          <h2 id="tv-trab" class="tv-h">Trabajadores de Cursor</h2>
          <TrabajadoresCursor />
        </section>
      </template>
    </div>
  </ViewFrame>

  <TareaForm :open="formAbierto" :programa="editando" :cursor-disponible="cursorOk" @close="formAbierto = false" />
  <TerminalPinSheet
    :open="pinAbierto"
    :busy="tareas.pinBusy"
    :error="tareas.pinError || null"
    :locked-until="bloqueadoHasta"
    :capa="90"
    title="Prender las tareas programadas"
    note="Van a correr solas, con permisos normales: lo que pida permiso te va a esperar."
    cta="Prender"
    @submit="confirmarPin"
    @close="pinAbierto = false"
  />
  <ConfirmSheet :open="!!porBorrar" :title="`¿Borrar «${porBorrar?.nombre ?? ''}»?`" confirm-label="Borrar" @confirm="confirmarBorrar" @cancel="porBorrar = null" />
</template>

<style scoped>
.tv { position: fixed; inset: 0; z-index: 80; background-image: radial-gradient(1000px 420px at 0% -10%, var(--accent-soft), transparent 60%); outline: none; overflow: hidden; }
.tv :deep(.vf-body) { flex: 1; min-height: 0; padding: 0; gap: 0; overflow: hidden; }
.tv-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--view-pad-top) var(--gutter) calc(40px + env(safe-area-inset-bottom));
  padding-left: max(var(--gutter), env(safe-area-inset-left));
  padding-right: max(var(--gutter), env(safe-area-inset-right));
  display: grid;
  gap: 18px;
  max-width: var(--read-max);
  width: 100%;
  margin: 0 auto;
  align-content: start;
}
.desk .tv-body { padding-top: 28px; }
.tv-mudo { margin: 0; color: var(--text-3, var(--text-2)); font-size: 13px; overflow-wrap: anywhere; }
.tv-global { padding: 14px; display: flex; align-items: center; gap: 12px; min-width: 0; }
.tv-global-txt { flex: 1; min-width: 0; display: grid; gap: 2px; }
.tv-switch { position: relative; flex: none; width: 46px; height: 28px; border: 0; padding: 0; border-radius: var(--r-pill); background: var(--bg-2); box-shadow: inset 0 0 0 1px var(--line-2); cursor: pointer; transition: background 0.2s; }
.tv-switch i { position: absolute; top: 3px; left: 3px; width: 22px; height: 22px; border-radius: 50%; background: var(--text-3); transition: transform 0.2s var(--ease-sheet, ease), background 0.2s; }
.tv-switch.on { background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.tv-switch.on i { transform: translateX(18px); background: var(--accent); }
.tv-sec { display: grid; gap: 8px; min-width: 0; }
.tv-sec-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.tv-acciones { display: flex; gap: 6px; }
.tv-h { margin: 0; font-family: var(--font-display); font-size: 17px; font-weight: 620; }
.tv-vacio { padding: 14px; }
.tv-lista { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; min-width: 0; }
.tv-prog { padding: 14px; display: grid; gap: 4px; min-width: 0; }
.tv-prog.pausada .tv-nombre { color: var(--text-3); }
.tv-prog-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.tv-nombre { min-width: 0; overflow-wrap: anywhere; }
.tv-chip { flex: none; font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: var(--r-pill); background: var(--accent-soft); color: var(--text-2); }
.tv-ruta { font-size: 12px; }
.tv-botones { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.tv-hist { gap: 0; }
.tv-corrida { display: flex; align-items: flex-start; gap: 10px; padding: 10px 14px; min-width: 0; }
.tv-corrida + .tv-corrida { border-top: 1px solid var(--line); }
.tv-corrida-txt { flex: 1; min-width: 0; display: grid; gap: 1px; }
.tv-estado { flex: none; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; background: var(--bg-2); color: var(--text-3); }
.tv-estado.ok { background: var(--st-done-soft); color: var(--st-done); }
.tv-estado.fallo { background: var(--danger-soft); color: var(--danger); }
.tv-estado.en_curso { color: var(--accent); }
</style>
