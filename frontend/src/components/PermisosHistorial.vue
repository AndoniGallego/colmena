<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import type { RegistroPermiso } from '../api/types'
import { filasHistorial } from '../lib/permisosHistorial'
import { registroPermisos } from '../state/app'

const items = ref<RegistroPermiso[]>([])
const loading = ref(true)
const error = ref(false)
const filas = computed(() => filasHistorial(items.value))

onMounted(async () => {
  try {
    items.value = (await registroPermisos()).items
  } catch {
    error.value = true
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="ui-card hist" aria-live="polite">
    <p v-if="loading" class="msg">Cargando…</p>
    <p v-else-if="error" class="msg" role="alert">No pude leer el historial</p>
    <p v-else-if="!filas.length" class="msg">Todavía no hay permisos decididos</p>
    <ul v-else class="lista">
      <li v-for="(f, i) in filas" :key="i" class="fila">
        <span class="top">
          <strong class="dec">{{ f.decision }}</strong>
          <span class="quien">{{ f.quien }}</span>
          <span v-if="f.hora" class="hora mono">{{ f.hora }}</span>
        </span>
        <span class="her mono">{{ f.herramienta || '—' }}<template v-if="f.detalle"> · {{ f.detalle }}</template></span>
        <span class="ses">en {{ f.sesion }}</span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.hist { padding: 4px 18px; }
.msg { margin: 0; padding: 16px 0; font-size: 13px; color: var(--text-3); }
.lista { margin: 0; padding: 0; list-style: none; }
.fila { display: grid; gap: 3px; padding: 14px 0; min-width: 0; }
.fila + .fila { border-top: 1px solid var(--line); }
.top { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 10px; }
.dec { font-size: 13px; font-weight: 580; color: var(--text); }
.quien, .ses { font-size: 12px; color: var(--text-3); }
.hora { font-size: 11px; color: var(--text-4); }
.her { font-size: 12px; color: var(--text-2); overflow-wrap: anywhere; }
</style>
