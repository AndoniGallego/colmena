<script setup lang="ts">
import { ref, watch } from 'vue'
import { etiquetaRango, type ComentarioDiff } from '../lib/diffComentarios'
import DiffComentarioSheet from './DiffComentarioSheet.vue'

const props = defineProps<{ open: boolean; comentarios: ComentarioDiff[] }>()
const emit = defineEmits<{ close: []; editar: [id: string, texto: string]; quitar: [id: string] }>()

const editando = ref('')
const borrador = ref('')

watch(() => props.open, (on) => { if (!on) editando.value = '' })

function empezar(c: ComentarioDiff) {
  editando.value = c.id
  borrador.value = c.texto
}
function guardar() {
  if (borrador.value.trim()) emit('editar', editando.value, borrador.value.trim())
  editando.value = ''
}
</script>

<template>
  <DiffComentarioSheet :open="open" titulo="Comentarios para la sesión" @close="emit('close')">
    <ol class="lista" data-test="comentarios-lista">
      <li v-for="(c, i) in comentarios" :key="c.id" class="item">
        <p class="cab mono">{{ i + 1 }}) {{ c.path }}:{{ etiquetaRango(c) }} <span class="lado">{{ c.lado === 'nuevo' ? 'nuevas' : 'borradas' }}</span></p>
        <template v-if="editando === c.id">
          <textarea v-model="borrador" class="texto" rows="3" maxlength="1000" aria-label="Comentario" />
          <div class="fila">
            <button type="button" class="btn btn-ghost" @click="editando = ''">Cancelar</button>
            <button type="button" class="btn btn-primary" :disabled="!borrador.trim()" data-test="comentario-guardar" @click="guardar">Guardar</button>
          </div>
        </template>
        <template v-else>
          <p class="txt">{{ c.texto }}</p>
          <div class="fila">
            <button type="button" class="btn btn-ghost btn-sm hit" data-test="comentario-editar" @click="empezar(c)">Editar</button>
            <button type="button" class="btn btn-danger-soft btn-sm hit" data-test="comentario-quitar" @click="emit('quitar', c.id)">Quitar</button>
          </div>
        </template>
      </li>
    </ol>
    <p v-if="!comentarios.length" class="vacio">No hay comentarios pendientes.</p>
    <div class="sheet-actions">
      <button type="button" class="btn btn-ghost" @click="emit('close')">Cerrar</button>
    </div>
  </DiffComentarioSheet>
</template>

<style scoped>
.lista { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; max-height: min(52dvh, 420px); overflow-y: auto; overscroll-behavior: contain; }
.item { display: grid; gap: 6px; padding: 10px 12px; border-radius: var(--r-md); background: var(--surface-2); border: 1px solid var(--line); }
.cab { margin: 0; font-size: 12px; color: var(--accent); overflow-wrap: anywhere; }
.lado { color: var(--text-4); }
.txt { margin: 0; font-size: 14px; line-height: 1.4; color: var(--text); overflow-wrap: anywhere; }
.texto { box-sizing: border-box; width: 100%; padding: 10px 12px; border-radius: var(--r-md); font: inherit; font-size: 16px; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; resize: vertical; }
.texto:focus { border-color: var(--accent); }
.fila { display: flex; gap: 8px; justify-content: flex-end; }
.vacio { margin: 0; font-size: 13px; color: var(--text-3); }
</style>
