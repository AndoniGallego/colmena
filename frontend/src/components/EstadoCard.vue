<script setup lang="ts">
import type { Estado } from '../lib/estado'
import EstadoLineas from './EstadoLineas.vue'

defineProps<{ data: Estado }>()
</script>

<template>
  <aside class="estado-card ui-card" aria-label="Estado de la sesión">
    <EstadoLineas :estado="data" />
  </aside>
</template>

<style scoped>
.estado-card {
  padding: 8px 12px;
  min-width: 0;
  background: var(--surface-2);
}
</style>
