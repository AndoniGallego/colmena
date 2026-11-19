<script setup lang="ts">
import { computed } from 'vue'
import { lineasEstado, type Estado } from '../lib/estado'

const props = defineProps<{ estado: Estado }>()
const lineas = computed(() => lineasEstado(props.estado))
</script>

<template>
  <div class="estado-lineas">
    <p v-for="l in lineas" :key="l.clave" :class="['estado-linea', `estado-${l.clave}`]">
      <span class="marca" aria-hidden="true">{{ l.marca }}</span>
      <span class="txt">{{ l.texto }}</span>
    </p>
  </div>
</template>

<style scoped>
.estado-lineas {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}
.estado-linea {
  display: flex;
  gap: 6px;
  margin: 0;
  min-width: 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-2);
}
.marca {
  flex: none;
  width: 1em;
  text-align: center;
  color: var(--text-3);
}
.txt {
  min-width: 0;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
}
.estado-hizo .marca {
  color: var(--st-done);
}
.estado-pide {
  color: var(--text);
  font-weight: 560;
}
.estado-pide .marca {
  color: var(--st-blocked);
}
</style>
