<script setup lang="ts">
import { computed } from 'vue'
import { abrirPedidoPestana, pedidosDeSesion, pedidosPestana, rechazarPedidoPestana } from '../state/pedidosPestana'
import PedidoPestanaCard from './PedidoPestanaCard.vue'

const props = defineProps<{ sessionId: string }>()
const pedidos = computed(() => pedidosDeSesion(props.sessionId))
</script>

<template>
  <TransitionGroup tag="div" name="ped" class="pedidos-chat" :class="{ vacio: !pedidos.length }" role="region" aria-label="Pedidos de esta sesión">
    <PedidoPestanaCard
      v-for="p in pedidos"
      :key="p.id"
      class="ped-item"
      :pedido="p"
      :busy="!!pedidosPestana.porId[p.id]?.enviando"
      :error="pedidosPestana.porId[p.id]?.error"
      :vista="pedidosPestana.porId[p.id]?.vista"
      @abrir="abrirPedidoPestana"
      @rechazar="rechazarPedidoPestana"
    />
  </TransitionGroup>
</template>

<style scoped>
.pedidos-chat {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 10px 0 6px;
  min-width: 0;
}
.pedidos-chat.vacio:not(:has(.ped-leave-active)) {
  display: none;
}
.ped-item {
  max-width: 100%;
  min-width: 0;
}
.ped-enter-active,
.ped-leave-active {
  transition: opacity 180ms ease-out, transform 180ms ease-out;
}
.ped-enter-from,
.ped-leave-to {
  opacity: 0;
  transform: translateY(4px);
}
@media (prefers-reduced-motion: reduce) {
  .ped-enter-from,
  .ped-leave-to {
    transform: none;
  }
}
</style>
