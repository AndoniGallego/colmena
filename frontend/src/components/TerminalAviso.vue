<script setup lang="ts">
import { computed } from 'vue'
import type { TerminalMotivo } from '../api/types'
import Icon from './Icon.vue'

const props = defineProps<{ motivo: TerminalMotivo; proceso: string }>()

const TEXTOS: Record<TerminalMotivo, { titulo: string; texto: (p: string) => string }> = {
  apagada: {
    titulo: 'Escribir está apagado',
    texto: () => 'La escritura en terminales está apagada en la notebook. Se prende desde la notebook, no desde la app. Mientras tanto solo se puede mirar.',
  },
  ocupada: {
    titulo: 'Ahora no espera un comando',
    texto: (p) => `Hay un programa corriendo${p ? ` (${p})` : ''}, o está pidiendo una contraseña. Esperá a que termine o frenalo con Ctrl+C para poder escribir.`,
  },
  desconocido: {
    titulo: 'No sé qué hay corriendo',
    texto: () => 'No pude saber si la terminal está esperando un comando, así que por ahora no se puede escribir. Se reintenta solo.',
  },
  protegido: {
    titulo: 'Solo se puede mirar',
    texto: () => 'Esta terminal está protegida: solo se puede mirar.',
  },
}

const t = computed(() => TEXTOS[props.motivo])
</script>

<template>
  <div class="aviso" :data-motivo="motivo" role="status">
    <span class="ic" aria-hidden="true"><Icon :name="motivo === 'ocupada' ? 'pause' : 'lock'" :size="16" /></span>
    <div class="tx">
      <p class="ti">{{ t.titulo }}</p>
      <p class="de">{{ t.texto(proceso) }}</p>
    </div>
  </div>
</template>

<style scoped>
.aviso {
  flex: none;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
  margin: 0;
  padding: 12px 14px calc(14px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--line);
  background: color-mix(in srgb, var(--st-blocked-soft) 55%, var(--bg));
}
.ic {
  flex: none;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: var(--r-md);
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
}
.tx { min-width: 0; flex: 1; }
.ti { margin: 0; font-size: 14px; font-weight: 600; color: var(--text); }
.de { margin: 2px 0 0; font-size: 13px; line-height: 1.4; color: var(--text-2); overflow-wrap: anywhere; }
@media (min-width: 1024px) { .aviso { padding: 12px 24px calc(14px + env(safe-area-inset-bottom)); } }
</style>
