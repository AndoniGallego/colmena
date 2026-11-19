<script setup lang="ts">
import BrandMark from './BrandMark.vue'
</script>

<template>
  <div class="logo-loader" role="status" aria-busy="true">
    <BrandMark :size="60" loader :intro="false" />
    <span class="sr-only">Cargando</span>
  </div>
</template>

<style scoped>
.logo-loader {
  display: grid;
  place-items: center;
  height: 100%;
  /* La gracia evita el parpadeo en cargas rápidas */
  animation: loader-in 0.35s var(--ease-out) 150ms both;
}
@keyframes loader-in {
  from { opacity: 0; }
}
</style>
