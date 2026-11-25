<script setup lang="ts">
import { computed, ref } from 'vue'
import type { PedidoPestana, VistaCierrePedido } from '../api/types'
import {
  ariaAceptarPedidoPestana,
  ariaRechazarPedidoPestana,
  botonPedidoPestana,
  conteoCierre,
  dondeCierre,
  hayMensajeParaClaude,
  mensajeLargo,
  nombreSesionPedidoPestana,
  recortarCarpeta,
  textoTrabajando,
  textoVencePedidoPestana,
  tituloPedidoPestana,
} from '../lib/pedidosPestana'
import { useNow } from '../lib/time'
import Icon from './Icon.vue'

const props = defineProps<{
  pedido: PedidoPestana
  busy?: boolean
  /** Campana / listas compactas */
  compact?: boolean
  /** Vista del notch: ancho completo, sin encabezado duplicado */
  notch?: boolean
  error?: string
  /** Solo pedidos de cierre: si la sesión está trabajando, el botón pasa a "Cerrar igual". */
  vista?: VistaCierrePedido
}>()

const emit = defineEmits<{ abrir: [id: string]; rechazar: [id: string] }>()

const now = useNow()
const sesion = computed(() => nombreSesionPedidoPestana(props.pedido))
const cierre = computed(() => (props.pedido.accion === 'cerrar' ? props.pedido.cierre : undefined))
const esCierre = computed(() => !!cierre.value)
const esCerrar = computed(() => props.pedido.accion === 'cerrar' && !cierre.value && !!props.pedido.terminal)
const cualquierCierre = computed(() => esCerrar.value || esCierre.value)
const objetivoTxt = computed(() => ({ sesion: 'sesión', pestana: 'pestaña', tarjeta: 'tarjeta' })[cierre.value?.objetivo ?? 'sesion'])
const trabajando = computed(() => esCierre.value && !!props.vista?.trabajando)
const avisoTrabajo = computed(() => `${textoTrabajando(props.vista?.estados ?? [])}. Si cerrás igual, no se le pide que guarde.`)
const conteo = computed(() => (cierre.value && cierre.value.objetivo !== 'sesion' ? conteoCierre(cierre.value) : ''))
const nota = computed(() => !trabajando.value && esCierre.value && (cierre.value?.sesiones ?? 0) > 0)
const botonTxt = computed(() => botonPedidoPestana(props.pedido, props.vista))
const botonAria = computed(() => ariaAceptarPedidoPestana(props.pedido, trabajando.value ? props.vista : undefined))
const noAria = computed(() => ariaRechazarPedidoPestana(props.pedido))
const donde = computed(() => (cierre.value ? dondeCierre(cierre.value) : ''))
const esCursor = computed(() => props.pedido.accion === 'cursor')
const esMensaje = computed(() => props.pedido.accion === 'mensaje')
const esProgramada = computed(() => props.pedido.accion === 'programada')
const esTarea = computed(() => props.pedido.accion === 'tarea')
const esMcp = computed(() => esMensaje.value || esProgramada.value || esTarea.value)
const esMulti = computed(
  () => !cualquierCierre.value && !esCursor.value && !esMcp.value && (props.pedido.pestanas?.length ?? 0) > 0,
)
const esAbrir1 = computed(() => !cualquierCierre.value && !esCursor.value && !esMcp.value && !esMulti.value)
const leyo = computed(() => props.pedido.leyo_otra_sesion?.nombre?.trim() ?? '')
const modeloCursor = computed(() => props.pedido.cursor?.modelo?.trim() ?? '')
const cursorLargo = computed(() => mensajeLargo(props.pedido.mensaje, 6, 360))
const cursorAbierto = ref(false)
const term = computed(() => props.pedido.terminal)
const termNombre = computed(() => term.value?.titulo || term.value?.proceso || 'Terminal')
const carpetas = computed(() => {
  if (!esMulti.value) {
    const t = props.pedido.carpeta.trim()
    if (props.notch) return t
    return recortarCarpeta(t, props.compact ? 36 : 56)
  }
  const unicas = [...new Set((props.pedido.pestanas ?? []).map((p) => p.carpeta.trim() || props.pedido.carpeta.trim()))]
  if (unicas.length === 1) return recortarCarpeta(unicas[0], props.compact ? 36 : 48)
  return `${unicas.length} carpetas`
})
const vence = computed(() => textoVencePedidoPestana(props.pedido.vence, Math.floor(now.value / 1000)))
const expandido = defineModel<boolean>('expandido', { default: false })

const msgCorto = computed(() => {
  const t = props.pedido.mensaje.trim()
  if (!props.compact || expandido.value || t.length <= 120) return t
  return `${t.slice(0, 120)}…`
})

const avisoSeguro = computed(
  () => !cualquierCierre.value && !esCursor.value && !esMensaje.value && !esProgramada.value && hayMensajeParaClaude(props.pedido),
)
const abiertos = ref<number[]>([])
function tabAbierta(i: number) {
  return abiertos.value.includes(i)
}
function alternarTab(i: number) {
  abiertos.value = tabAbierta(i) ? abiertos.value.filter((x) => x !== i) : [...abiertos.value, i]
}

const resumen = computed(() => {
  if (!esMulti.value) return ''
  const n = props.pedido.pestanas!.length
  const tarj = props.pedido.tarjeta?.trim()
  if (tarj) return `Tarjeta nueva «${tarj}» con ${n} pestañas`
  return `${n} pestañas en la tarjeta de origen`
})

function iconoTipo(tipo: 'claude' | 'terminal') {
  return tipo === 'claude' ? 'sparkle' : 'terminal'
}

function onAbrir() {
  if (props.busy) return
  emit('abrir', props.pedido.id)
}

function onRechazar() {
  if (props.busy) return
  emit('rechazar', props.pedido.id)
}
</script>

<template>
  <article class="ppc" :class="{ compact, notch, multi: esMulti }">
    <header v-if="!notch" class="top">
      <span class="kicker"><Icon :name="cualquierCierre ? 'close' : esCursor ? 'sparkle' : 'terminal'" :size="13" /> {{ esCierre || esMcp ? tituloPedidoPestana(pedido) : esCerrar ? 'Cerrar terminal' : esCursor ? 'Trabajador Cursor' : 'Pedido de pestaña' }}</span>
      <span class="vence mono">{{ vence }}</span>
    </header>
    <p class="sesion">
      <b>{{ sesion }}</b>
      <template v-if="esCierre"> pide cerrar una {{ objetivoTxt }}</template>
      <template v-else-if="esCerrar"> pide cerrar una terminal</template>
      <template v-else-if="esCursor"> pide un trabajador Cursor</template>
      <template v-else-if="esMensaje"> pide mandarle un mensaje a «{{ pedido.envio?.nombre || pedido.envio?.pane_id }}»</template>
      <template v-else-if="esProgramada">
        pide programar un mensaje para las {{ pedido.programada?.cuando }} a «{{ pedido.programada?.nombre || pedido.programada?.pane_id }}»
      </template>
      <template v-else-if="esTarea"> pide una tarea para {{ pedido.tarea?.ticket }}</template>
      <template v-else-if="esMulti"> pide {{ pedido.pestanas!.length }} pestañas</template>
      <template v-else> pide abrir una pestaña</template>
      <span v-if="notch" class="vence mono sesion-vence">{{ vence }}</span>
    </p>
    <p v-if="leyo" class="leyo">Antes de pedir esto, leyó la sesión «{{ leyo }}»</p>
    <p v-if="esMulti && resumen" class="tarjeta-nom">{{ resumen }}</p>
    <div v-if="cierre" class="term">
      <p v-if="donde" class="term-donde mono">{{ donde }}</p>
      <p class="term-nom">{{ cierre.label }}</p>
      <p v-if="cierre.carpeta" class="term-cwd mono" :title="cierre.carpeta">{{ recortarCarpeta(cierre.carpeta, compact ? 36 : 56) }}</p>
      <span v-if="conteo" class="term-chip mono">{{ conteo }}</span>
    </div>
    <div v-if="esCierre" role="status" class="trabajo-vivo">
      <Transition name="aviso-trabajo">
        <p v-if="trabajando" class="trabajo">{{ avisoTrabajo }}</p>
      </Transition>
    </div>
    <p v-if="nota" class="seguro">Antes de cerrar, se le pide a cada sesión de Claude que guarde lo que tenía.</p>
    <div v-if="esCerrar && term" class="term">
      <p v-if="term.donde" class="term-donde mono">{{ term.donde }}</p>
      <p class="term-nom">{{ termNombre }}</p>
      <p v-if="term.cwd" class="term-cwd mono" :title="term.cwd">{{ recortarCarpeta(term.cwd, compact ? 36 : 56) }}</p>
      <span class="term-chip mono" :class="term.estado"><i class="dot" />{{ term.estado === 'prompt' ? 'en el prompt' : term.proceso || 'corriendo' }}</span>
    </div>
    <p v-if="esAbrir1 || esCursor || esTarea" class="carpeta mono" :title="pedido.carpeta">{{ carpetas }}</p>
    <div v-if="esCursor" class="cursor-ped">
      <p v-if="pedido.nombre?.trim()" class="cursor-nom">{{ pedido.nombre }}</p>
      <blockquote class="tab-quote cursor-quote">
        <span class="tab-quote-et">Pedido para Cursor (lo escribió otra sesión)</span>
        <span class="cursor-msg" :class="{ recortado: cursorLargo && !cursorAbierto }">{{ pedido.mensaje }}</span>
        <button v-if="cursorLargo" type="button" class="ver hit" @click="cursorAbierto = !cursorAbierto">
          {{ cursorAbierto ? 'Ver menos' : 'Ver todo' }}
        </button>
      </blockquote>
      <p v-if="modeloCursor" class="cursor-modelo">Modelo <span class="mono">{{ modeloCursor }}</span></p>
      <p class="seguro">Cursor va a editar archivos en una copia aparte; solo corre los comandos que tu configuración de Cursor permite.</p>
    </div>
    <ul v-if="esMulti" class="tabs">
      <li v-for="(p, i) in pedido.pestanas" :key="i">
        <Icon :name="iconoTipo(p.tipo)" :size="13" class="ico-tipo" />
        <span class="tab-nom">{{ p.nombre }}</span>
        <span class="tab-cwd mono" :title="p.carpeta || pedido.carpeta">{{
          recortarCarpeta(p.carpeta || pedido.carpeta, compact ? 28 : 40)
        }}</span>
        <code v-if="p.comando" class="tab-cmd mono">{{ p.comando }}</code>
        <blockquote v-if="p.tipo === 'claude' && p.mensaje?.trim()" class="tab-quote">
          <span class="tab-quote-et">Mensaje para Claude (lo escribió otra sesión)</span>
          <span class="tab-msg" :class="{ recortado: mensajeLargo(p.mensaje) && !tabAbierta(i) }">{{ p.mensaje }}</span>
          <button v-if="mensajeLargo(p.mensaje)" type="button" class="ver hit" @click="alternarTab(i)">
            {{ tabAbierta(i) ? 'Ver menos' : 'Ver todo' }}
          </button>
        </blockquote>
      </li>
    </ul>
    <blockquote v-if="esMcp && pedido.mensaje.trim()" class="tab-quote cursor-quote">
      <span class="tab-quote-et">{{ esTarea ? 'Nota para la tarea' : 'Mensaje' }} (lo escribió otra sesión)</span>
      <span class="cursor-msg" :class="{ recortado: cursorLargo && !cursorAbierto }">{{ pedido.mensaje }}</span>
      <button v-if="cursorLargo" type="button" class="ver hit" @click="cursorAbierto = !cursorAbierto">
        {{ cursorAbierto ? 'Ver menos' : 'Ver todo' }}
      </button>
    </blockquote>
    <div v-if="esAbrir1" class="msg-wrap" :class="{ compact: compact && !expandido }">
      <pre class="msg">{{ compact ? msgCorto : pedido.mensaje }}</pre>
    </div>
    <button
      v-if="esAbrir1 && compact && pedido.mensaje.trim().length > 120"
      type="button"
      class="ver"
      @click="expandido = !expandido"
    >
      {{ expandido ? 'Ver menos' : 'Ver todo' }}
    </button>
    <p v-if="avisoSeguro" class="seguro">Las sesiones nuevas van a arrancar preguntando antes de cada herramienta.</p>
    <p v-if="error" class="err" role="alert">{{ error }}</p>
    <div class="actions">
      <button
        type="button"
        class="btn primary hit"
        :disabled="busy"
        :class="{ peligro: cualquierCierre }"
        :aria-label="botonAria"
        @click="onAbrir"
      >
        {{ botonTxt }}
      </button>
      <button
        type="button"
        class="btn ghost hit"
        :disabled="busy"
        :aria-label="noAria"
        @click="onRechazar"
      >
        No
      </button>
    </div>
  </article>
</template>

<style scoped>
.ppc {
  display: grid;
  gap: 8px;
  min-width: 0;
  text-align: left;
}
.ppc.compact {
  gap: 6px;
}
.top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.kicker {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--t-xs);
  font-weight: 600;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-3);
}
.vence {
  font-size: 11px;
  color: var(--text-4);
}
.sesion {
  margin: 0;
  font-size: 14px;
  line-height: 1.35;
  color: var(--text);
}
.term {
  display: grid;
  gap: 2px;
  min-width: 0;
  padding: 9px 11px;
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  background: var(--surface-2);
}
.term p {
  margin: 0;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.term-donde {
  font-size: 11px;
  color: var(--text-4);
}
.term-nom {
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
}
.term-cwd {
  font-size: 12px;
  color: var(--text-3);
}
.term-chip {
  justify-self: start;
  margin-top: 4px;
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 22px;
  padding: 0 9px;
  border-radius: var(--r-pill);
  font-size: 11px;
  color: var(--text-2);
  background: var(--st-idle-soft);
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
.term-chip .dot { flex: none; width: 6px; height: 6px; border-radius: 50%; background: var(--st-idle); }
.term-chip.corriendo { color: var(--st-working); background: var(--st-working-soft); }
.term-chip.corriendo .dot { background: var(--st-working); }
.term-chip.prompt .dot { background: var(--st-done); }
.tarjeta-nom {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
}
.carpeta {
  margin: 0;
  font-size: 12px;
  color: var(--accent);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tabs {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 6px;
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  background: var(--surface-2);
  padding: 8px 10px;
  max-height: min(32vh, 240px);
  overflow: auto;
  overscroll-behavior: contain;
}
.tabs li {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: baseline;
  gap: 6px 8px;
  font-size: 12px;
  line-height: 1.35;
}
.ico-tipo {
  color: var(--text-3);
  flex: none;
}
.tab-nom {
  font-weight: 600;
  color: var(--text);
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tab-cwd {
  font-size: 11px;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  max-width: 42%;
  justify-self: end;
}
.tab-cmd {
  grid-column: 2 / -1;
  font-size: 11px;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tab-quote {
  grid-column: 2 / -1;
  display: grid;
  gap: 3px;
  min-width: 0;
  margin: 2px 0 0;
  padding: 4px 0 4px 9px;
  border-left: 2px solid var(--line-2);
}
.tab-quote-et {
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--text-4);
}
.tab-msg {
  font-family: var(--font-mono);
  font-size: 11px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-2);
}
.tab-msg.recortado {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  overflow: hidden;
}
.tab-quote .ver {
  font-size: 11px;
}
.cursor-ped {
  display: grid;
  gap: 6px;
  min-width: 0;
}
.cursor-nom {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  overflow-wrap: anywhere;
}
.cursor-quote {
  grid-column: auto;
}
.cursor-msg {
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-2);
}
.cursor-msg.recortado {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 6;
  line-clamp: 6;
  overflow: hidden;
}
.cursor-quote .ver {
  justify-self: start;
  font-size: 11px;
}
.cursor-modelo {
  margin: 0;
  font-size: 12px;
  color: var(--text-3);
}
/* Región viva siempre montada; sin caja propia para no sumar un hueco en la grilla. */
.trabajo-vivo {
  display: contents;
}
.trabajo {
  margin: 0;
  padding: 8px 11px;
  border-radius: var(--r-md);
  font-size: 12px;
  line-height: 1.35;
  color: var(--st-working);
  background: var(--st-working-soft);
}
.aviso-trabajo-enter-active {
  transition: opacity 0.18s ease-out;
}
.aviso-trabajo-enter-from {
  opacity: 0;
}
.leyo {
  margin: 0;
  font-size: 12px;
  line-height: 1.35;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
.seguro {
  margin: 0;
  font-size: 12px;
  line-height: 1.35;
  color: var(--text-3);
}
.msg-wrap {
  max-height: min(28vh, 220px);
  overflow: auto;
  overscroll-behavior: contain;
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  background: var(--surface-2);
}
.msg-wrap.compact {
  max-height: 3.2em;
  overflow: hidden;
}
.msg {
  margin: 0;
  padding: 10px 12px;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
  color: var(--text-2);
}
.ver {
  justify-self: start;
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  padding: 0;
}
.err {
  margin: 0;
  font-size: 12px;
  color: var(--st-blocked);
}
.actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.btn {
  min-height: 36px;
  padding: 0 14px;
  border-radius: var(--r-pill);
  font-size: 13px;
  font-weight: 600;
  transition: filter 0.2s, scale 0.25s var(--spring);
}
.btn:disabled {
  opacity: 0.55;
}
.btn:active:not(:disabled) {
  scale: var(--press-scale);
}
.primary {
  background: var(--accent);
  color: var(--accent-ink);
}
.primary.peligro {
  background: var(--danger);
  color: var(--danger-ink);
}
.ghost {
  color: var(--text-2);
  border: 1px solid var(--line-2);
  background: var(--surface);
}
.ppc.notch .sesion {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ppc.notch .sesion b {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.ppc.notch .sesion-vence {
  margin-left: auto;
  flex: none;
  font-size: 11px;
  color: var(--text-4);
}
.ppc.notch .actions {
  flex-wrap: nowrap;
}
.ppc.notch .tabs {
  max-height: 5.5em;
}
.ppc.multi.notch .tabs {
  max-height: 7em;
}
@media (prefers-reduced-motion: reduce) {
  .aviso-trabajo-enter-active {
    transition-duration: 0.01ms;
  }
}
</style>
