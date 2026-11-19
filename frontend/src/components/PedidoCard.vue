<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PedidoPermiso } from '../api/types'
import { MENSAJE_ESTADO, detalleEntrada } from '../lib/pedidoCard'
import Icon from './Icon.vue'

const props = defineProps<{ pedido: PedidoPermiso; busy?: boolean; done?: boolean; changed?: boolean }>()
const emit = defineEmits<{ permitir: [id: string]; rechazar: [id: string, motivo: string]; siempre: [id: string] }>()

const motivo = ref('')
const mostrarRegla = ref(false)
const abierto = computed(() => props.pedido.estado === 'abierto')
const detalle = computed(() => detalleEntrada(props.pedido))
const aviso = computed(() => MENSAJE_ESTADO[props.pedido.estado])
const puede = computed(() => abierto.value && !props.busy && !props.done && !props.changed)

function onPermitir() {
  if (!puede.value) return
  emit('permitir', props.pedido.id)
}

function onRechazar() {
  if (!puede.value) return
  emit('rechazar', props.pedido.id, motivo.value)
}

function onSiempre() {
  if (!puede.value || !props.pedido.regla) return
  if (!mostrarRegla.value) {
    mostrarRegla.value = true
    return
  }
  emit('siempre', props.pedido.id)
}
</script>

<template>
  <div class="pc stagger">
    <div class="top">
      <span class="kicker mono">permiso</span>
      <span class="tool mono">{{ pedido.herramienta }}</span>
      <span v-if="done" class="stamp mono"><Icon name="check" :size="12" /> Respondido</span>
    </div>
    <h2 class="title">Quiere usar {{ pedido.herramienta }}</h2>
    <pre v-if="detalle" class="code mono">{{ detalle }}</pre>

    <p v-if="aviso" class="info">{{ aviso }}</p>

    <template v-else-if="abierto">
      <div v-if="mostrarRegla && pedido.regla" class="regla">
        <p class="regla-t">Regla que se guarda</p>
        <p class="mono regla-c">{{ pedido.regla.contenido }}</p>
        <p class="mono regla-a">{{ pedido.regla.archivo }}</p>
        <button type="button" class="btn always" :disabled="!puede" @click="onSiempre">Confirmar y pedir PIN</button>
      </div>
      <template v-else>
        <label class="motivo">
          <span class="motivo-l">Motivo (opcional, al rechazar)</span>
          <textarea v-model="motivo" rows="2" placeholder="Por qué no" :disabled="!puede" />
        </label>
        <div class="actions">
          <button type="button" class="btn primary" :disabled="!puede" @click="onPermitir">Permitir</button>
          <button type="button" class="btn ghost" :disabled="!puede" @click="onRechazar">Rechazar</button>
          <button v-if="pedido.regla" type="button" class="btn always" :disabled="!puede" @click="onSiempre">Permitir siempre</button>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.pc {
  display: grid;
  gap: 10px;
  min-width: 0;
}
.top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.kicker {
  font-size: var(--t-xs);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--st-blocked);
}
.tool {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 6px;
  color: var(--text-3);
  background: var(--bg-2);
  border: 1px solid var(--line);
}
.stamp {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--t-xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--st-done);
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--st-done) 45%, transparent);
}
.title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.code {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  line-height: 1.55;
  color: var(--text);
  background: var(--bg-2);
  border: 1px solid var(--line);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 16em;
  overflow: auto;
  overscroll-behavior: contain;
  min-width: 0;
}
.info {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  color: var(--text-2);
}
.motivo {
  display: grid;
  gap: 6px;
}
.motivo-l {
  font-size: 12px;
  color: var(--text-3);
}
.motivo textarea {
  width: 100%;
  resize: none;
  padding: 10px 12px;
  border-radius: 12px;
  font: inherit;
  font-size: 16px;
  line-height: 1.45;
  color: var(--text);
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  outline: none;
}
.regla {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--r-md);
  background: var(--bg-2);
  border: 1px solid var(--line);
}
.regla-t {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
}
.regla-c,
.regla-a {
  margin: 0;
  font-size: var(--t-md);
  overflow-wrap: anywhere;
  color: var(--text);
}
.regla-a {
  color: var(--text-3);
}
.actions {
  display: grid;
  gap: 8px;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 46px;
  padding: 0 16px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 620;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.primary {
  background: var(--accent);
  color: var(--accent-ink);
}
.ghost {
  color: var(--text-2);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.always {
  height: 40px;
  font-size: var(--t-lg);
  color: var(--st-blocked);
  background: transparent;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--st-blocked) 40%, transparent);
}
@media (min-width: 640px) {
  .actions {
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    align-items: center;
  }
  .btn {
    height: 40px;
  }
}
</style>
