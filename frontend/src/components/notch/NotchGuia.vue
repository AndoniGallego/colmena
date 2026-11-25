<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { guia, pedir, preguntaGuia, puedeSiguiente, seguirViva, siguiente, terminar, textoCajita } from '../../state/guia'

/** `saliendo`: la guía se cerró y la cajita sigue montada solo para animar su salida. */
withDefaults(defineProps<{ saliendo?: boolean }>(), { saliendo: false })
const emit = defineEmits<{ cerrar: [] }>()

const MAX_PREGUNTA = 300

const pregunta = ref('')
const campo = ref<HTMLInputElement | null>(null)

const texto = computed(() => textoCajita(guia.value))
const ocupada = computed(() => guia.value.estado === 'preparando' || guia.value.estado === 'mirando')
const bloqueado = computed(() => ocupada.value || guia.value.estado === 'reunion')
const hayError = computed(() => guia.value.estado === 'error' || guia.value.estado === 'reunion')
const verSiguiente = computed(() => puedeSiguiente(guia.value))
const verListo = computed(() => guia.value.estado === 'fin')
const verSalir = computed(() => seguirViva(guia.value) && guia.value.estado !== 'fin')

function enviar() {
  const limpia = pregunta.value.trim()
  if (!limpia || bloqueado.value) return
  pregunta.value = ''
  void pedir(limpia)
}

function onKey(e: KeyboardEvent) {
  if (e.isComposing) return
  if (e.key === 'Enter') {
    e.preventDefault()
    enviar()
  } else if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    emit('cerrar')
  }
}

const enfocarCampo = () => campo.value?.focus({ preventScroll: true })

// En Windows la ventana del notch recibe el foco después de montar la cajita (Ctrl+Alt+V): el cursor vuelve al campo.
onMounted(() => {
  enfocarCampo()
  window.addEventListener('focus', enfocarCampo)
})
onBeforeUnmount(() => window.removeEventListener('focus', enfocarCampo))
</script>

<template>
  <section class="guia" :class="{ saliendo }" :inert="saliendo || undefined" aria-label="Guía">
    <div class="campo">
      <input
        ref="campo"
        v-model="pregunta"
        type="text"
        :maxlength="MAX_PREGUNTA"
        :disabled="bloqueado"
        aria-label="¿Qué querés hacer?"
        placeholder="¿Qué querés hacer?"
        enterkeyhint="send"
        autocomplete="off"
        spellcheck="false"
        @keydown="onKey"
      />
      <p v-if="preguntaGuia" class="pregunta"><span class="vh">Preguntaste: </span>{{ preguntaGuia }}</p>
      <p class="estado" :class="{ error: hayError, loop: ocupada }" role="status">{{ texto }}</p>
      <div v-if="verSiguiente || verListo || verSalir" class="acciones">
        <button v-if="verSiguiente" type="button" class="primaria" @click="siguiente()">Hecho, siguiente</button>
        <button v-if="verListo" type="button" class="primaria" @click="terminar()">Listo</button>
        <button v-if="verSalir" type="button" class="salir" @click="terminar()">Salir</button>
      </div>
      <div class="pie"><span><kbd>Enter</kbd> pregunta · <kbd>Esc</kbd> oculta</span></div>
    </div>
  </section>
</template>

<style scoped>
.guia {
  display: grid;
}
.campo {
  --entra: cubic-bezier(0.2, 0, 0, 1);
  --sale: cubic-bezier(0.4, 0, 1, 1);
  position: relative;
  margin: 2px 0 8px;
  padding: 10px;
  background: linear-gradient(180deg, var(--accent-soft), transparent 55%), var(--surface);
  border-radius: var(--r-lg);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transform-origin: 50% 0%;
  animation: campo-entra 220ms var(--entra) both;
}
/* Borde lima que se enciende al abrir y queda tenue, como el marco de la abejita. */
.campo::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: inset 0 0 0 1px var(--accent-line);
  opacity: 0;
  pointer-events: none;
  animation: borde-enciende 600ms 90ms var(--entra) both;
}
.saliendo .campo {
  animation: campo-sale 180ms var(--sale) forwards;
}
@keyframes campo-entra {
  from {
    opacity: 0;
    transform: translateY(-6px) scale(0.97);
  }
}
@keyframes campo-sale {
  to {
    opacity: 0;
    transform: translateY(-4px) scale(0.97);
  }
}
@keyframes borde-enciende {
  0% {
    opacity: 0;
  }
  45% {
    opacity: 1;
  }
  100% {
    opacity: 0.5;
  }
}
@keyframes campo-funde {
  from {
    opacity: 0;
  }
}
@keyframes campo-funde-sale {
  to {
    opacity: 0;
  }
}
:root[data-motion='soft'] .campo {
  animation: campo-funde 150ms ease-out both;
}
:root[data-motion='soft'] .saliendo .campo {
  animation: campo-funde-sale 150ms ease-out forwards;
}
input {
  display: block;
  width: 100%;
  min-height: 44px;
  padding: 2px;
  border: 0;
  outline: 0;
  background: transparent;
  color: var(--text);
  caret-color: var(--accent);
  font: 16px/1.4 var(--font-ui);
}
input::placeholder {
  color: var(--text-4);
}
input:disabled {
  color: var(--text-3);
}
.pregunta {
  margin: 2px 2px 0;
  padding-left: 8px;
  box-shadow: inset 2px 0 0 var(--accent-line);
  font: 500 var(--t-sm)/1.3 var(--font-ui);
  color: var(--text);
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.vh {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}
.estado {
  margin: 4px 2px 0;
  min-height: 1.3em;
  font: 500 var(--t-sm)/1.3 var(--font-ui);
  color: var(--text-2);
  overflow-wrap: anywhere;
  text-wrap: pretty;
  font-variant-numeric: tabular-nums;
}
.estado.error {
  color: var(--danger);
}
.estado.loop {
  color: var(--miel);
  animation: respira 1.4s ease-in-out infinite;
}
@keyframes respira {
  50% {
    opacity: 0.55;
  }
}
.acciones {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
button {
  position: relative;
  height: 32px;
  padding: 0 12px;
  border: 0;
  border-radius: var(--r-sm);
  font: 600 var(--t-sm) var(--font-ui);
  cursor: pointer;
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out,
    scale 150ms ease-out;
}
button::before {
  content: '';
  position: absolute;
  inset: -6px -2px;
}
.primaria {
  background: var(--accent);
  color: var(--accent-ink);
}
.salir {
  background: transparent;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
button:active {
  scale: var(--press-scale);
}
button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.pie {
  margin-top: 8px;
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
@media (prefers-reduced-motion: reduce) {
  .campo {
    animation: campo-funde 150ms ease-out both;
  }
  .campo::after {
    animation: none;
    opacity: 0.5;
  }
  .saliendo .campo {
    animation: none;
    opacity: 0;
  }
  .estado.loop {
    animation: none;
  }
}
@media (hover: hover) and (pointer: fine) {
  .primaria:hover {
    background: color-mix(in srgb, var(--accent) 86%, white);
  }
  .salir:hover {
    color: var(--text);
    background: var(--surface-hover);
  }
}
</style>
