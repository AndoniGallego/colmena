<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { gsap, isSoft, useGsap } from '../motion'
import { abrirMudarTodas, mz, quietas, retomar } from '../state/mudanza'
import Icon from './Icon.vue'

const { run } = useGsap()
const shown = ref(false)

function enter(node: Element, done: () => void) {
  if (isSoft() || shown.value) return done()
  shown.value = true
  run(() => gsap.fromTo(node, { y: 8, opacity: 0 }, { y: 0, opacity: 1, duration: 0.5, ease: 'power3.out', clearProps: 'transform,opacity', onComplete: done }))
}
onMounted(() => (shown.value = false))
</script>

<template>
  <div v-if="(mz.disponible && quietas.length) || mz.pendientes.length" class="wrap">
    <Transition :css="false" @enter="enter">
      <button v-if="mz.disponible && quietas.length" type="button" class="lchip" @click="abrirMudarTodas()">
        <Icon name="terminal" :size="14" />
        <span>Mudar todas las quietas ({{ quietas.length }})</span>
        <Icon name="chevron" :size="12" class="arr" />
      </button>
    </Transition>
    <div v-for="p in mz.pendientes" :key="p.id" class="aviso">
      <p v-if="p.estado === 'sin_confirmar'">No pude confirmar que «{{ p.nombre }}» se cerró en Herdr, así que no la abrí en tu terminal propia. Fijate que no siga abierta allá.</p>
      <p v-else>«{{ p.nombre }}» se cerró en Herdr pero no arrancó en tu terminal propia. La conversación no se perdió.</p>
      <button type="button" class="aviso-btn" :disabled="mz.ocupado" @click="retomar(p)">Volver a abrir</button>
    </div>
  </div>
</template>

<style scoped>
.wrap {
  display: grid;
  justify-items: start;
  gap: 8px;
  margin-bottom: 0;
}
.lchip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 40px;
  max-width: 100%;
  margin: 0;
  padding: 0 14px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--text-2);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s, background 0.2s;
}
.lchip:hover {
  color: var(--text);
  border-color: color-mix(in srgb, var(--accent) 50%, transparent);
}
.arr {
  opacity: 0.6;
}
.aviso {
  display: grid;
  gap: 8px;
  padding: 10px 14px;
  border-radius: var(--r-lg);
  border: 1px solid var(--st-blocked);
  background: color-mix(in srgb, var(--st-blocked) 8%, var(--bg-2));
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-2);
}
.aviso p {
  margin: 0;
}
.aviso-btn {
  justify-self: start;
  padding: 6px 12px;
  border-radius: var(--r-pill);
  font-size: var(--t-md);
  font-weight: 560;
  color: var(--text);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: opacity 0.2s;
}
.aviso-btn:disabled {
  opacity: 0.5;
}
</style>
