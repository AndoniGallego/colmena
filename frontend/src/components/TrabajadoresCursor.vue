<script setup lang="ts">
import { onMounted, onUnmounted, ref } from 'vue'
import { httpCursorApi, type CursorApi, type CursorEstado, type EstadoTrabajador, type TrabajadorCursor } from '../api/cursorApi'
import { ApiError } from '../api/types'
import { recortarCarpeta } from '../lib/pedidosPestana'
import { EVENTO_CURSOR } from '../lib/tareas'

const props = withDefaults(defineProps<{ api?: CursorApi; ahora?: () => number }>(), {
  api: () => httpCursorApi,
  ahora: () => Math.floor(Date.now() / 1000),
})

const lista = ref<TrabajadorCursor[]>([])
const estado = ref<CursorEstado | null>(null)
const cargando = ref(false)
const error = ref('')
const logs = ref<Record<string, string>>({})
const ocupado = ref<string | null>(null)

const ETIQUETA: Record<EstadoTrabajador, string> = {
  corriendo: 'Trabajando',
  ok: 'Terminó',
  error: 'Terminó con error',
  vencido: 'Se pasó de tiempo',
  cancelado: 'Cancelado',
  interrumpido: 'Interrumpido',
}

function mensaje(e: unknown) {
  return e instanceof ApiError && e.detail ? e.detail : 'No pude hablar con Colmena'
}

async function cargar() {
  cargando.value = true
  error.value = ''
  try {
    const [l, e] = await Promise.all([props.api.getTrabajadores(), props.api.getCursorEstado()])
    lista.value = l
    estado.value = e
  } catch (e) {
    error.value = mensaje(e)
  } finally {
    cargando.value = false
  }
}

function duracion(t: TrabajadorCursor) {
  const fin = t.fin ?? props.ahora()
  const min = Math.max(0, Math.floor((fin - t.inicio) / 60))
  if (min < 1) return 'menos de 1 min'
  if (min < 60) return `${min} min`
  return `${Math.floor(min / 60)} h ${min % 60} min`
}

function archivos(t: TrabajadorCursor) {
  const n = t.archivos.length
  return n === 1 ? '1 archivo' : `${n} archivos`
}

async function alternarLog(t: TrabajadorCursor) {
  if (t.id in logs.value) {
    const resto = { ...logs.value }
    delete resto[t.id]
    logs.value = resto
    return
  }
  ocupado.value = t.id
  try {
    logs.value = { ...logs.value, [t.id]: await props.api.getLog(t.id) }
  } catch (e) {
    error.value = mensaje(e)
  } finally {
    ocupado.value = null
  }
}

async function cancelar(t: TrabajadorCursor) {
  ocupado.value = t.id
  try {
    await props.api.postCancelar(t.id)
  } catch (e) {
    error.value = mensaje(e)
  } finally {
    ocupado.value = null
  }
  await cargar()
}

function alCambiarCursor() {
  void cargar()
}
onMounted(() => {
  void cargar()
  window.addEventListener(EVENTO_CURSOR, alCambiarCursor)
})
onUnmounted(() => window.removeEventListener(EVENTO_CURSOR, alCambiarCursor))
</script>

<template>
  <section class="tc">
    <header class="tc-top">
      <span v-if="estado" class="tc-cupo mono">{{ estado.corriendo }} de {{ estado.max_simultaneos }} trabajando</span>
      <button type="button" class="btn btn-sm ghost hit" :disabled="cargando" @click="cargar">Actualizar</button>
    </header>
    <p v-if="estado && !estado.disponible" class="tc-nota">No encuentro cursor-agent en la notebook.</p>
    <p v-if="error" class="tc-err" role="alert">{{ error }}</p>
    <p v-if="!cargando && !error && !lista.length" class="tc-nota">No hay trabajadores Cursor.</p>
    <ul v-if="lista.length" class="tc-lista">
      <li v-for="t in lista" :key="t.id" class="tc-item">
        <div class="tc-fila">
          <span class="tc-estado" :class="t.estado"><i class="dot" />{{ ETIQUETA[t.estado] }}</span>
          <span class="tc-dur mono">{{ duracion(t) }}</span>
        </div>
        <p class="tc-nom">{{ t.nombre }}</p>
        <p class="tc-meta mono" :title="t.ruta">{{ t.rama }} · {{ recortarCarpeta(t.ruta, 40) }}</p>
        <p v-if="t.origen.nombre" class="tc-meta">Lo pidió {{ t.origen.nombre }}</p>
        <p v-if="t.estado !== 'corriendo'" class="tc-meta">{{ archivos(t) }}<template v-if="t.log_recortado"> · log recortado</template></p>
        <p v-if="t.resumen" class="tc-resumen">{{ t.resumen }}</p>
        <div class="tc-acc">
          <button type="button" class="btn btn-sm ghost hit" :disabled="ocupado === t.id" @click="alternarLog(t)">
            {{ t.id in logs ? 'Ocultar log' : 'Ver log' }}
          </button>
          <button
            v-if="t.estado === 'corriendo'"
            type="button"
            class="btn btn-sm ghost hit peligro"
            :disabled="ocupado === t.id"
            @click="cancelar(t)"
          >
            Cancelar
          </button>
        </div>
        <pre v-if="t.id in logs" class="log mono">{{ logs[t.id] || 'El log está vacío.' }}</pre>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.tc {
  display: grid;
  gap: 10px;
  min-width: 0;
}
.tc-top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.tc-cupo {
  font-size: var(--t-xs);
  color: var(--text-4);
}
.tc-top .btn {
  margin-left: auto;
}
.tc-nota,
.tc-err {
  margin: 0;
  font-size: var(--t-sm);
  color: var(--text-3);
}
.tc-err {
  color: var(--danger, var(--text));
}
.tc-lista {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.tc-item {
  display: grid;
  gap: 4px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  background: var(--surface-2);
}
.tc-fila {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.tc-estado {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--text-2);
}
.tc-estado .dot {
  width: 7px;
  height: 7px;
  border-radius: var(--r-pill);
  background: var(--text-4);
}
.tc-estado.corriendo .dot {
  background: var(--accent, var(--text-2));
}
.tc-estado.error .dot,
.tc-estado.vencido .dot {
  background: var(--danger, var(--text-2));
}
.tc-dur {
  font-size: var(--t-xs);
  color: var(--text-4);
}
.tc-nom {
  margin: 0;
  font-size: var(--t-lg);
  font-weight: 600;
  color: var(--text);
  overflow-wrap: anywhere;
}
.tc-meta {
  margin: 0;
  font-size: var(--t-xs);
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tc-resumen {
  margin: 0;
  font-size: var(--t-sm);
  line-height: 1.4;
  color: var(--text-2);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.tc-acc {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}
.log {
  max-height: min(40vh, 320px);
  margin: 0;
  padding: 8px 10px;
  overflow: auto;
  overscroll-behavior: contain;
  border-radius: var(--r-sm);
  border: 1px solid var(--line);
  background: var(--surface);
  font-size: var(--t-2xs);
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-2);
}
</style>
