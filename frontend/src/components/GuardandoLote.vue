<script setup lang="ts">
import { computed } from 'vue'
import type { Guardado, GuardadoAccion } from '../api/types'
import { leyenda, paneEstadoLabel, puedeEsperarMas, targetEstadoLabel } from '../lib/guardado'

const props = defineProps<{ lote: Guardado; ocupado?: boolean }>()
const emit = defineEmits<{ accion: [GuardadoAccion] }>()

const varios = computed(() => props.lote.targets.length > 1)
</script>

<template>
  <section class="gl" role="status" aria-live="polite" :data-vencido="lote.vencido || undefined">
    <p class="gl-k mono">Guardando antes de cerrar</p>
    <p class="gl-t">{{ leyenda(lote) }}</p>
    <ul class="gl-targets">
      <li v-for="t in lote.targets" :key="t.key" class="gl-target" :data-estado="t.estado">
        <p v-if="varios || t.estado !== 'guardando'" class="gl-name">
          <b>{{ t.label }}</b> <span class="mono">{{ targetEstadoLabel(t.estado) }}</span>
        </p>
        <p v-if="t.error" class="gl-err">{{ t.error }}</p>
        <ul class="gl-panes">
          <li v-for="p in t.panes" :key="p.pane_id" :data-estado="p.estado">
            <span class="gl-dot" aria-hidden="true" />
            <span class="gl-pane">{{ p.titulo || p.pane_id }}</span>
            <span class="gl-st mono">{{ paneEstadoLabel(p.estado) }}</span>
          </li>
        </ul>
      </li>
    </ul>
    <div v-if="lote.puede_cerrar_igual || puedeEsperarMas(lote)" class="gl-acts">
      <button type="button" class="gl-btn danger" :disabled="ocupado || !lote.puede_cerrar_igual" @click="emit('accion', 'cerrar_igual')">Cerrar igual</button>
      <button v-if="puedeEsperarMas(lote)" type="button" class="gl-btn" :disabled="ocupado" @click="emit('accion', 'esperar_mas')">Esperar más</button>
    </div>
  </section>
</template>

<style scoped>
.gl {
  display: grid;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
  background: var(--bg-2);
  border: 1px solid var(--line);
}
.gl[data-vencido] {
  border-color: color-mix(in srgb, var(--st-blocked) 55%, transparent);
  background: var(--st-blocked-soft);
}
.gl-k {
  margin: 0;
  font-size: 10px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--st-blocked);
}
.gl-t,
.gl-name,
.gl-err {
  margin: 0;
  font-size: 13px;
  color: var(--text-2);
}
.gl-err {
  color: var(--danger);
}
.gl-targets,
.gl-panes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 4px;
}
.gl-panes li {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  min-width: 0;
}
.gl-dot {
  flex: none;
  width: 7px;
  height: 7px;
  border-radius: var(--r-pill);
  background: var(--st-working);
}
li[data-estado='listo'] .gl-dot {
  background: var(--st-done, var(--accent));
}
li[data-estado='bloqueado'] .gl-dot,
li[data-estado='fallo'] .gl-dot {
  background: var(--st-blocked);
}
.gl-pane {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.gl-st {
  flex: none;
  color: var(--text-4);
  font-size: 11px;
}
.gl-acts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.gl-btn {
  height: 32px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  font-size: 13px;
  background: var(--bg-3, var(--bg-2));
  color: var(--text-2);
  border: 1px solid var(--line);
}
.gl-btn.danger {
  background: var(--danger);
  color: var(--danger-ink);
  border-color: transparent;
}
.gl-btn:disabled {
  opacity: 0.45;
  pointer-events: none;
}
</style>
