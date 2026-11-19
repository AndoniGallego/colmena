<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { boardState } from '../state/app'
import { mostrarFranja } from '../lib/sinConexion'

const conn = computed(() => boardState.value.connection)
const desdeMs = ref<number | null>(null)
const ahoraMs = ref(Date.now())
let tick: ReturnType<typeof setInterval> | undefined

watch(
  conn,
  (c, prev) => {
    if (c === 'live') {
      desdeMs.value = null
      clearInterval(tick)
      tick = undefined
      return
    }
    if (prev === 'live' || desdeMs.value === null) desdeMs.value = Date.now()
    if (!tick) tick = setInterval(() => (ahoraMs.value = Date.now()), 1000)
  },
  { immediate: true },
)

const visible = computed(() => mostrarFranja(conn.value, desdeMs.value, ahoraMs.value))

onBeforeUnmount(() => clearInterval(tick))
</script>

<template>
  <div v-if="visible" class="sin-conn" role="status">
    <span class="dot" aria-hidden="true"><i /></span>
    Sin conexión, reintentando…
  </div>
</template>

<style scoped>
.sin-conn {
  display: none;
}
@media (max-width: 639px) {
  .sin-conn {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    position: sticky;
    top: 0;
    z-index: 4;
    width: 100%;
    padding: 6px 12px;
    font-size: 13px;
    color: var(--st-blocked);
    background: var(--st-blocked-soft);
  }
  .dot {
    display: inline-flex;
    align-items: center;
  }
  .dot i {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--st-blocked);
    animation: blink 1s steps(2, jump-none) infinite;
  }
}
@keyframes blink {
  50% { opacity: 0.25; }
}
:root[data-motion='soft'] .dot i {
  animation: none;
}
</style>
