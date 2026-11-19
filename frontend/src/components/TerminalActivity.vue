<script setup lang="ts">
import { onMounted } from 'vue'
import { actividad, loadActividad } from '../state/terminalActions'
import Icon from './Icon.vue'

defineEmits<{ close: [] }>()

const LABEL: Record<string, string> = {
  ctrl_c: 'Ctrl+C',
  repetir_ejecutar: 'Repetir',
  repetir_cancelar: 'Repetir cancelado',
  repetir_preparar: 'Repetir preparado',
  comando: 'Comando',
  ventana_abierta: 'Escritura abierta',
  ventana_pin_fallido: 'PIN incorrecto',
  ventana_vencida: 'Escritura vencida',
  ventana_cerrada: 'Escritura cerrada',
  rechazo: 'Rechazado',
}
const label = (a: string) => LABEL[a] ?? a
function when(ts: string): string {
  const d = new Date(ts)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString('es', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' })
}
onMounted(() => void loadActividad())
</script>

<template>
  <aside class="act" aria-label="Actividad de terminales">
    <header>
      <h2>Actividad</h2>
      <button type="button" class="x" aria-label="Cerrar actividad" @click="$emit('close')"><Icon name="close" :size="15" /></button>
    </header>
    <p v-if="!actividad.length" class="empty">Todavía no hay acciones registradas.</p>
    <ul v-else>
      <li v-for="(e, i) in actividad" :key="e.ts + i" :class="{ bad: !e.ok }">
        <span class="when mono">{{ when(e.ts) }}</span>
        <span class="what">{{ label(e.accion) }}<template v-if="e.workspace"> en {{ e.workspace }}</template></span>
        <code v-if="e.comando">{{ e.comando }}</code>
        <span v-if="e.error" class="err">{{ e.error }}</span>
        <span v-if="e.dispositivo" class="dev mono">{{ e.dispositivo }}</span>
      </li>
    </ul>
  </aside>
</template>

<style scoped>
.act { position: absolute; z-index: 5; top: 0; right: 0; bottom: 0; width: min(100%, 380px); display: flex; flex-direction: column; background: var(--surface); border-left: 1px solid var(--line-2); box-shadow: var(--shadow-pop); animation: slide 0.4s var(--spring) both; }
@keyframes slide { from { transform: translateX(24px); opacity: 0; } }
header { display: flex; align-items: center; justify-content: space-between; padding: 14px 14px 10px 18px; border-bottom: 1px solid var(--line); }
h2 { margin: 0; font-family: var(--font-display); font-size: 16px; font-weight: 600; }
.x { width: 32px; height: 32px; border-radius: var(--r-md); display: grid; place-items: center; color: var(--text-2); }
.x:hover { background: var(--surface-hover); }
.empty { margin: 0; padding: 20px 18px; color: var(--text-3); font-size: 13px; }
ul { list-style: none; margin: 0; padding: 6px 0; overflow-y: auto; }
li { display: grid; gap: 3px; padding: 10px 18px; border-bottom: 1px solid var(--line); min-width: 0; }
.when, .dev { font-size: 11px; color: var(--text-4); }
.what { font-size: var(--t-lg); font-weight: 600; }
li.bad .what { color: var(--danger); }
code { font-family: var(--font-mono); font-size: 12px; color: var(--text-2); overflow-wrap: anywhere; }
.err { font-size: 12px; color: var(--danger); }
@media (prefers-reduced-motion: reduce) { .act { animation: none; } }
</style>
