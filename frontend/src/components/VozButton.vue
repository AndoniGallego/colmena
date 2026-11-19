<script setup lang="ts">
import { computed } from 'vue'
import type { Voz } from '../state/voz'
import { SHORTCUT_LABEL } from '../lib/voz'
import Icon from './Icon.vue'

const props = defineProps<{ voz: Voz; disabled?: boolean; size?: number; fill?: boolean }>()

const phase = computed(() => props.voz.snap.value.phase)
const recording = computed(() => phase.value === 'recording')
const working = computed(() => phase.value === 'requesting' || phase.value === 'transcribing')
const label = computed(() => {
  if (recording.value) return 'Terminar y transcribir'
  if (phase.value === 'requesting') return 'Esperando el permiso del micrófono'
  if (phase.value === 'transcribing') return 'Transcribiendo'
  return 'Dictar con el micrófono'
})
const tip = computed(() => (recording.value ? `Terminar (${SHORTCUT_LABEL}) · Esc cancela` : `Dictar (${SHORTCUT_LABEL}). El audio se transcribe en tu notebook y nunca se envía solo.`))

function press() {
  if (working.value && phase.value !== 'requesting') return
  props.voz.toggle()
}
</script>

<template>
  <button
    type="button"
    class="mic hit"
    :class="{ rec: recording, work: working, err: phase === 'error', fill, keycap: fill }"
    :style="size ? { width: size + 'px', height: size + 'px' } : undefined"
    :aria-pressed="recording"
    :aria-label="label"
    :title="tip"
    :disabled="disabled || phase === 'transcribing'"
    @click.stop="press"
  >
    <span v-if="recording" class="halo" aria-hidden="true" />
    <span v-if="phase === 'transcribing' || phase === 'requesting'" class="spin" aria-hidden="true" />
    <Icon v-else-if="recording" name="stop" :size="15" />
    <Icon v-else name="mic" :size="17" />
  </button>
</template>

<style scoped>
.mic {
  position: relative;
  flex: none;
  width: 36px;
  height: 36px;
  border-radius: var(--r-md);
  display: grid;
  place-items: center;
  color: var(--text-3);
  transition: color 0.2s, background 0.25s, scale 0.35s var(--spring), box-shadow 0.3s;
}
.mic.fill {
  width: 100%;
  height: 100%;
  min-height: 40px;
  border-radius: var(--r-md);
  transition: color 0.2s, background 0.25s, translate 0.3s var(--spring), box-shadow 0.3s var(--spring);
}
.mic.fill:active:not(:disabled) {
  scale: 1;
}
.mic.fill:hover:not(:disabled):not(.rec) {
  background: linear-gradient(var(--keycap-top), var(--keycap) 22px);
}
.mic:hover:not(:disabled):not(.rec) {
  color: var(--text);
  background: var(--surface-hover);
}
.mic:active:not(:disabled) {
  scale: var(--press-scale);
}
.mic.err {
  color: var(--danger);
}
.mic.work {
  color: var(--accent);
}
.mic.rec {
  background: var(--danger);
  color: var(--danger-ink);
  box-shadow: 0 0 0 3px var(--danger-soft);
}
.mic:disabled {
  opacity: 0.4;
  cursor: default;
}
.mic.work:disabled {
  opacity: 0.9;
}
.halo {
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--danger);
  opacity: 0.5;
  animation: halo 1.6s var(--ease-out) infinite;
  pointer-events: none;
}
.mic > :not(.halo) {
  position: relative;
}
.spin {
  width: 15px;
  height: 15px;
  border-radius: 50%;
  border: 1.5px solid currentColor;
  border-right-color: transparent;
  animation: spin 0.8s linear infinite;
}
@keyframes halo {
  from { transform: scale(1); opacity: 0.5; }
  to { transform: scale(1.7); opacity: 0; }
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
:root[data-motion='soft'] .halo {
  animation: none;
}
</style>
