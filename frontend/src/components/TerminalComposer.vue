<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError } from '../api/types'
import { MAX_COMANDO, validarComando } from '../lib/terminales'
import { enviados, openAccion, tconfig } from '../state/terminalActions'
import { clearHistorial, closeVentana, countdown, guardVentana, historial, openVentana, pinProblem, ventanaAbierta } from '../state/terminalWrite'
import EnterKey from './EnterKey.vue'
import Icon from './Icon.vue'
import TerminalPinSheet from './TerminalPinSheet.vue'

const props = defineProps<{ paneId: string; prompt: boolean; proceso: string }>()

const text = ref('')
const problem = ref<string | null>(null)
const showHistory = ref(false)
const input = ref<HTMLInputElement | null>(null)
const pin = ref({ open: false, busy: false, error: null as string | null, lockedUntil: null as number | null })
let pending: { text: string; rapido: number | null } | null = null

const rapidos = computed(() => tconfig.value?.comandos_rapidos ?? [])
const clock = computed(() => `${Math.floor(countdown.value / 60)}:${String(countdown.value % 60).padStart(2, '0')}`)
const low = computed(() => countdown.value > 0 && countdown.value <= 30)
const placeholder = computed(() => (props.prompt ? 'Escribí un comando' : `Hay un programa corriendo${props.proceso ? ` (${props.proceso})` : ''}: frenalo primero`))

onMounted(guardVentana)
watch(enviados, () => {
  text.value = ''
  problem.value = null
})
watch(text, () => (problem.value = null))
watch(
  () => props.paneId,
  () => {
    text.value = ''
    showHistory.value = false
  },
)
onBeforeUnmount(() => {
  pin.value.open = false
})

function submit(value = text.value, rapido: number | null = null) {
  if (!props.prompt) return
  const bad = validarComando(value)
  if (bad) {
    problem.value = bad
    return
  }
  showHistory.value = false
  if (!ventanaAbierta.value) {
    pending = { text: value, rapido }
    pin.value = { open: true, busy: false, error: null, lockedUntil: null }
    return
  }
  void openAccion('comando', props.paneId, value.normalize('NFC'), rapido)
}

async function onPin(value: string) {
  pin.value.busy = true
  pin.value.error = null
  try {
    await openVentana(value)
  } catch (e) {
    const p = pinProblem(e)
    pin.value.error = p.message
    pin.value.lockedUntil = p.retryAfter ? Date.now() + p.retryAfter * 1000 : null
    if (e instanceof ApiError && e.status === 403) pin.value.open = false
    pin.value.busy = false
    return
  }
  pin.value = { open: false, busy: false, error: null, lockedUntil: null }
  const next = pending
  pending = null
  if (next) void openAccion('comando', props.paneId, next.text.normalize('NFC'), next.rapido)
}

function cancelPin() {
  pin.value.open = false
  pending = null
}

function pick(cmd: string) {
  text.value = cmd
  showHistory.value = false
  input.value?.focus()
}
</script>

<template>
  <div class="comp">
    <div v-if="ventanaAbierta" class="open" :class="{ low }" role="status">
      <Icon name="lock" :size="13" />
      <span class="mono">Escritura abierta</span>
      <b class="mono">{{ clock }}</b>
      <button type="button" class="close hit" @click="closeVentana()">Cerrar escritura</button>
    </div>

    <div v-if="rapidos.length" class="chips" role="group" aria-label="Comandos rápidos">
      <button v-for="(c, i) in rapidos" :key="c + i" type="button" class="chip mono" :disabled="!prompt" @click="submit(c, i)">{{ c }}</button>
    </div>

    <Transition name="pop">
      <div v-if="showHistory" class="hist" role="listbox" aria-label="Historial">
        <p v-if="!historial.length" class="empty">Todavía no hay comandos en el historial.</p>
        <button v-for="c in historial" :key="c" type="button" class="h mono" role="option" @click="pick(c)">{{ c }}</button>
        <button v-if="historial.length" type="button" class="clear" @click="clearHistorial()"><Icon name="trash" :size="13" /> Borrar historial</button>
      </div>
    </Transition>

    <p v-if="problem" class="problem" role="alert"><Icon name="warn" :size="13" /> {{ problem }}</p>

    <form class="row" @submit.prevent="submit()">
      <input
        ref="input"
        v-model="text"
        class="in mono"
        type="text"
        :placeholder="placeholder"
        :disabled="!prompt"
        :maxlength="MAX_COMANDO + 50"
        autocomplete="off"
        autocapitalize="off"
        autocorrect="off"
        spellcheck="false"
        enterkeyhint="send"
        aria-label="Comando"
      />
      <EnterKey :disabled="!prompt || !text" label="Enviar comando">
        <button type="button" class="hbtn keycap" aria-label="Historial" :aria-expanded="showHistory" @click="showHistory = !showHistory"><Icon name="list" :size="16" /></button>
      </EnterKey>
    </form>

    <TerminalPinSheet :open="pin.open" :busy="pin.busy" :error="pin.error" :locked-until="pin.lockedUntil" @submit="onPin" @close="cancelPin" />
  </div>
</template>

<style scoped>
.comp { position: relative; flex: none; display: grid; gap: 8px; padding: 10px 12px calc(12px + env(safe-area-inset-bottom)); border-top: 1px solid var(--line); background: var(--bg); }
.open { display: flex; align-items: center; gap: 8px; height: 30px; padding: 0 6px 0 11px; border-radius: var(--r-pill); font-size: var(--t-sm); color: var(--st-blocked); background: var(--st-blocked-soft); justify-self: start; max-width: 100%; transition: color 0.3s, background 0.3s; }
.open b { font-weight: 600; font-variant-numeric: tabular-nums; }
.open.low { color: var(--danger); background: var(--danger-soft); }
.open.low b { animation: beat 1s ease-in-out infinite; }
@keyframes beat { 50% { opacity: 0.45; } }
.close { margin-left: 4px; height: 22px; padding: 0 10px; border-radius: var(--r-pill); font-size: 11px; font-weight: 600; color: inherit; box-shadow: inset 0 0 0 1px currentColor; transition: background 0.2s; }
.close:hover { background: color-mix(in srgb, currentColor 14%, transparent); }
.chips { display: flex; gap: 6px; overflow-x: auto; scrollbar-width: none; margin: 0 -2px; padding: 1px 2px; }
.chips::-webkit-scrollbar { display: none; }
.chip { flex: none; height: 28px; padding: 0 11px; border-radius: var(--r-md); font-size: 12px; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line-2); transition: color 0.2s, background 0.2s, scale 0.3s var(--spring); }
.chip:hover:not(:disabled) { color: var(--text); background: var(--accent-soft); }
.chip:active:not(:disabled) { scale: var(--press-scale); }
.chip:disabled { opacity: 0.4; cursor: not-allowed; }
.hist { position: absolute; left: 12px; right: 12px; bottom: calc(100% - 4px); max-height: 240px; overflow-y: auto; display: grid; padding: 6px; border-radius: var(--r-lg); background: var(--surface); border: 1px solid var(--line-2); box-shadow: var(--shadow-pop); z-index: 3; }
.h { text-align: left; padding: 8px 10px; border-radius: 8px; font-size: var(--t-md); color: var(--text-2); overflow-wrap: anywhere; }
.h:hover { background: var(--surface-hover); color: var(--text); }
.empty { margin: 0; padding: 10px; font-size: var(--t-md); color: var(--text-3); }
.clear { display: inline-flex; align-items: center; gap: 7px; margin-top: 4px; padding: 8px 10px; border-radius: 8px; font-size: 12px; color: var(--danger); border-top: 1px solid var(--line); }
.clear:hover { background: var(--danger-soft); }
.problem { display: flex; align-items: center; gap: 7px; margin: 0; font-size: var(--t-md); color: var(--danger); }
.row { display: flex; align-items: flex-end; gap: 8px; }
.hbtn { flex: none; width: 100%; height: 100%; min-height: 40px; display: grid; place-items: center; color: var(--text-3); }
.hbtn:hover, .hbtn[aria-expanded='true'] { color: var(--text); }
.in { flex: 1; min-width: 0; height: 44px; margin-bottom: 3px; padding: 0 13px; border-radius: 12px; font-size: 16px; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; transition: border-color 0.2s, box-shadow 0.25s; }
.in::placeholder { color: var(--text-4); font-size: 13px; }
.in:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.in:disabled { opacity: 0.55; cursor: not-allowed; }
@media (min-width: 1024px) { .comp { padding: 12px 24px 14px; } .in { font-size: 14px; height: 40px; } }
.pop-enter-active { transition: transform 0.4s var(--spring), opacity 0.2s; }
.pop-leave-active { transition: opacity 0.15s; }
.pop-enter-from { transform: translateY(8px) scale(0.98); opacity: 0; }
.pop-leave-to { opacity: 0; }
@media (prefers-reduced-motion: reduce) { .open.low b { animation: none; } }
:root[data-motion='soft'] .open.low b {
  animation: none;
}
@media (pointer: coarse) {
  .chip { min-height: 44px; }
  .h { min-height: 44px; }
  .clear { min-height: 44px; }
}
</style>
