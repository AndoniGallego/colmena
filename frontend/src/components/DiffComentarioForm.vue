<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { MAX_TEXTO } from '../lib/diffComentarios'
import { coincideCtrlOCmd } from '../lib/teclas'
import { capturandoAtajo, comboDe } from '../state/atajosEstado'

const props = defineProps<{ etiqueta: string; fragmento: string; modelValue: string; editando?: boolean; autoenfocar?: boolean }>()
const emit = defineEmits<{ 'update:modelValue': [v: string]; agregar: []; cancelar: [] }>()

const ta = ref<HTMLTextAreaElement | null>(null)
const valido = () => props.modelValue.trim().length > 0

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape') {
    e.preventDefault()
    e.stopPropagation()
    emit('cancelar')
  } else if (!capturandoAtajo.value && coincideCtrlOCmd(e, comboDe('comentar')) && valido()) {
    e.preventDefault()
    emit('agregar')
  }
}

onMounted(() => {
  if (props.autoenfocar) ta.value?.focus({ preventScroll: true })
})
</script>

<template>
  <form class="dcf" data-test="comentario-form" @submit.prevent="valido() && emit('agregar')">
    <p class="rango mono">{{ etiqueta }}</p>
    <pre v-if="fragmento" class="frag mono" data-test="comentario-fragmento">{{ fragmento }}</pre>
    <textarea
      ref="ta"
      class="texto"
      data-test="comentario-texto"
      rows="3"
      :maxlength="MAX_TEXTO"
      :value="modelValue"
      placeholder="Qué querés que cambie"
      aria-label="Comentario"
      @input="emit('update:modelValue', ($event.target as HTMLTextAreaElement).value)"
      @keydown="onKey"
    />
    <div class="acciones">
      <button type="button" class="btn btn-ghost" data-test="comentario-cancelar" @click="emit('cancelar')">Cancelar</button>
      <button type="submit" class="btn btn-primary" data-test="comentario-agregar" :disabled="!valido()">{{ editando ? 'Guardar' : 'Agregar' }}</button>
    </div>
  </form>
</template>

<style scoped>
.dcf { display: grid; gap: 8px; min-width: 0; padding: 10px; border-radius: var(--r-md); background: var(--surface); border: 1px solid var(--line-2); text-align: left; white-space: normal; font-family: var(--font-body, inherit); }
.rango { margin: 0; font-size: 12px; font-weight: 600; color: var(--accent); }
.frag { margin: 0; max-height: calc(4 * 1.45em + 12px); overflow: auto; padding: 6px 8px; border-radius: var(--r-sm, 8px); background: var(--bg-2); font-size: 12px; line-height: 1.45; color: var(--text-2); white-space: pre-wrap; overflow-wrap: anywhere; }
.texto { box-sizing: border-box; width: 100%; min-height: 76px; padding: 10px 12px; border-radius: var(--r-md); font: inherit; font-size: 16px; line-height: 1.4; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; resize: vertical; }
.texto:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.acciones { display: flex; flex-direction: row-reverse; gap: 8px; }
.acciones .btn { flex: 1; min-height: 44px; touch-action: manipulation; }
@media (min-width: 640px) {
  .acciones { justify-content: flex-start; }
  .acciones .btn { flex: none; min-height: 0; }
}
</style>
