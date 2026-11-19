<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import type { TipoNota } from '../../api/types'
import { mensajeError } from '../../lib/errores'
import { encolar, esSinRed } from '../../lib/notasCola'
import { crearNota } from '../../state/notas'

const emit = defineEmits<{ guardada: [r: { tipo: TipoNota; sinConexion: boolean }]; cerrar: [] }>()

const SIN_CONEXION = 'sin conexión, la guardo cuando vuelva'
const TIPOS: { tipo: TipoNota; etiqueta: string }[] = [
  { tipo: 'apunte', etiqueta: 'Apunte' },
  { tipo: 'recordatorio', etiqueta: 'Para hacer' },
]

const tipo = ref<TipoNota>('recordatorio')
const texto = ref('')
const error = ref('')
const aviso = ref('')
const enviando = ref(false)
const campo = ref<HTMLTextAreaElement | null>(null)

function enfocar() {
  campo.value?.focus({ preventScroll: true })
}

function elegir(t: TipoNota) {
  tipo.value = t
  error.value = ''
  enfocar()
}

function alternarTipo() {
  elegir(tipo.value === 'recordatorio' ? 'apunte' : 'recordatorio')
}

async function guardar() {
  const limpio = texto.value.trim()
  if (!limpio || enviando.value) return
  enviando.value = true
  error.value = ''
  const nota = { tipo: tipo.value, texto: limpio }
  let sinConexion = false
  try {
    await crearNota(nota)
  } catch (e) {
    if (!esSinRed(e)) {
      error.value = mensajeError(e, 'No pude guardar la nota. Probá de nuevo.')
      enviando.value = false
      enfocar()
      return
    }
    encolar(nota)
    sinConexion = true
    aviso.value = SIN_CONEXION
  }
  texto.value = ''
  emit('guardada', { tipo: nota.tipo, sinConexion })
}

function onKey(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'Tab' && !e.shiftKey) {
    e.preventDefault()
    alternarTipo()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    emit('cerrar')
  } else if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    void guardar()
  }
}

onMounted(() => {
  enfocar()
  window.addEventListener('focus', enfocar)
})

onBeforeUnmount(() => {
  window.removeEventListener('focus', enfocar)
})
</script>

<template>
  <div class="campo">
    <div class="tipos" role="group" aria-label="Tipo de nota">
      <button
        v-for="t in TIPOS"
        :key="t.tipo"
        type="button"
        :aria-pressed="tipo === t.tipo"
        @mousedown.prevent
        @click="elegir(t.tipo)"
      >{{ t.etiqueta }}</button>
    </div>
    <textarea
      ref="campo"
      v-model="texto"
      rows="2"
      maxlength="4000"
      aria-label="Texto de la nota"
      placeholder="Anotá algo…"
      enterkeyhint="done"
      :readonly="enviando"
      @keydown="onKey"
      @input="error = ''"
    />
    <p v-if="error" class="cap-msg cap-error" role="alert">{{ error }}</p>
    <p v-else-if="aviso" class="cap-msg cap-aviso" role="status">{{ aviso }}</p>
    <div class="campo-pie"><span><kbd>Enter</kbd> guarda · <kbd>Esc</kbd> cierra</span></div>
  </div>
</template>

<style scoped>
.campo {
  margin: 2px 0 8px;
  padding: 10px;
  background: var(--surface);
  border-radius: var(--r-lg);
  box-shadow: inset 0 0 0 1px var(--line-2);
  animation: campo-entra 180ms var(--ease-out) both;
}
@keyframes campo-entra {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
}
@keyframes campo-funde {
  from {
    opacity: 0;
  }
}
:root[data-motion='soft'] .campo {
  animation: campo-funde 150ms ease-out both;
}
@media (prefers-reduced-motion: reduce) {
  .campo {
    animation: campo-funde 150ms ease-out both;
  }
}
.tipos {
  display: inline-flex;
  gap: 2px;
  margin-bottom: 8px;
  padding: 2px;
  background: var(--bg);
  border-radius: var(--r-sm);
}
.tipos button {
  position: relative;
  height: 26px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--r-xs);
  background: transparent;
  color: var(--text-3);
  font: 500 var(--t-sm) var(--font-ui);
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out,
    scale 150ms ease-out;
}
.tipos button::before {
  content: '';
  position: absolute;
  inset: -9px -1px;
}
.tipos button[aria-pressed='true'] {
  background: var(--surface-2);
  color: var(--text);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.4);
}
.tipos button:active {
  scale: var(--press-scale);
}
.tipos button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
@media (hover: hover) and (pointer: fine) {
  .tipos button[aria-pressed='false']:hover {
    color: var(--text-2);
  }
}
textarea {
  display: block;
  width: 100%;
  min-height: 44px;
  padding: 2px;
  border: 0;
  outline: 0;
  resize: none;
  background: transparent;
  color: var(--text);
  caret-color: var(--accent);
  font: 16px/1.4 var(--font-ui);
}
textarea::placeholder {
  color: var(--text-4);
}
.campo-pie {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
  font-size: var(--t-sub-size);
  color: var(--text-4);
}
kbd {
  padding: 1px 5px;
  border-radius: var(--r-xs);
  box-shadow: inset 0 0 0 1px var(--line-2);
  color: var(--text-3);
  font: 500 var(--t-2xs) var(--font-mono);
}
.cap-msg {
  margin: 4px 2px 0;
  font: 500 var(--t-xs)/1.3 var(--font-ui);
}
.cap-error {
  color: var(--danger);
}
.cap-aviso {
  color: var(--miel);
}
</style>
