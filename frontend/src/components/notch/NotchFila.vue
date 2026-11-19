<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { FormaRespuesta } from '../../lib/notchRespuesta'
import { opcionesApiladas, type SesionNotch } from '../../lib/notchCeldas'
import { MENSAJE_CAMBIO, MENSAJE_ENVIADO, type EstadoFila } from '../../state/notchRespuesta'
import { marcarRetenerRespuestaAviso } from '../../state/notchRespuesta'
import { esCampoTextoNotch } from '../../lib/notchTeclado'
import { ago } from '../../lib/time'

const props = defineProps<{
  sesion: SesionNotch
  now: number
  forma?: FormaRespuesta
  estado?: EstadoFila
  activa?: boolean
}>()

const emit = defineEmits<{
  abrir: [sid: string]
  activar: [sid: string]
  opcion: [i: number]
  texto: [t: string]
  permiso: [accion: 'permitir' | 'rechazar']
  pedido: [accion: 'aceptar' | 'rechazar', pedidoId: string]
}>()

const otroAbierto = ref(false)
onBeforeUnmount(() => marcarRetenerRespuestaAviso(false))
const textoLibre = ref('')
const inputLibre = ref<HTMLInputElement | null>(null)
const opcionElegida = ref<number | null>(null)

const textoLibreOk = computed(() => textoLibre.value.trim().length > 0)

watch(otroAbierto, (abierto) => {
  if (abierto) nextTick(() => inputLibre.value?.focus())
  else if (!textoLibreOk.value) marcarRetenerRespuestaAviso(false)
})

function toggleOtro() {
  otroAbierto.value = !otroAbierto.value
}

function cerrarOtro(e: KeyboardEvent) {
  e.stopPropagation()
  otroAbierto.value = false
  textoLibre.value = ''
  marcarRetenerRespuestaAviso(false)
}

function onFocusLibre() {
  marcarRetenerRespuestaAviso(true)
}

function onInputLibre() {
  marcarRetenerRespuestaAviso(true)
}

function onBlurLibre() {
  marcarRetenerRespuestaAviso(textoLibreOk.value)
}

function clickOpcion(i: number) {
  if (bloqueado()) return
  opcionElegida.value = i
  emit('opcion', i)
}

const dotVar = {
  'te-toca': '--st-blocked',
  trabajando: '--st-working',
  termino: '--st-done',
  tranquila: '--mark-dim',
} as const

const busy = () => props.estado?.fase === 'enviando'
const bloqueado = () => busy() || props.estado?.fase === 'enviado' || props.estado?.fase === 'cambio' || props.estado?.fase === 'error'

function clickRow() {
  if (props.sesion.estado !== 'te-toca') emit('abrir', props.sesion.session_id)
}

function onRowKeydown(e: KeyboardEvent) {
  if (e.key !== 'Enter' && e.key !== ' ') return
  if (esCampoTextoNotch(e.target)) return
  e.preventDefault()
  clickRow()
}

function enviarTexto() {
  const t = textoLibre.value.trim()
  if (!t || bloqueado()) return
  emit('texto', t)
  textoLibre.value = ''
  otroAbierto.value = false
  marcarRetenerRespuestaAviso(false)
}

function preguntaDe(forma: FormaRespuesta): string {
  if (forma.tipo === 'opciones') return forma.pregunta
  if (forma.tipo === 'permiso') return forma.titulo
  return ''
}

const actsApiladas = computed(() => {
  const f = props.forma
  if (!f || f.tipo !== 'opciones') return false
  return opcionesApiladas(f.opciones)
})

const formaPedido = computed(() => (props.forma?.tipo === 'pedido' ? props.forma : null))

const trasElegirOpcion = computed(() => bloqueado() && opcionElegida.value !== null)
</script>

<template>
  <div
    class="row"
    :class="{ need: sesion.estado === 'te-toca' }"
    :role="sesion.estado === 'te-toca' ? undefined : 'button'"
    :tabindex="sesion.estado === 'te-toca' ? -1 : 0"
    :aria-busy="busy() ? 'true' : undefined"
    @click="clickRow"
    @keydown="onRowKeydown"
  >
    <span class="dot" :style="{ '--c': `var(${dotVar[sesion.estado]})` }" aria-hidden="true" />
    <div class="main">
      <div class="l1">
        <template v-if="sesion.estado === 'te-toca'">
          <div class="need-head">
            <div class="need-title-row">
              <button
                type="button"
                class="titulo"
                title="Abrir en Colmena"
                :aria-label="`Abrir ${sesion.titulo} en Colmena`"
                @click.stop="emit('abrir', sesion.session_id)"
              >
                <span class="titulo-text">{{ sesion.titulo }}</span>
                <svg class="titulo-flecha" width="11" height="11" viewBox="0 0 11 11" aria-hidden="true">
                  <path
                    d="M4.5 1.5h5v5M9.5 1.5L2 9"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
              <span class="when">{{ ago(sesion.last_activity, now) }}</span>
            </div>
            <span class="where">{{ sesion.donde }}</span>
          </div>
        </template>
        <template v-else>
          <strong>{{ sesion.titulo }}</strong>
          <span class="ws">{{ sesion.donde }}</span>
        </template>
      </div>
      <template v-if="estado?.fase === 'enviado'">
        <p class="sent">{{ MENSAJE_ENVIADO }}</p>
      </template>
      <template v-else-if="sesion.estado === 'te-toca' && formaPedido">
        <p class="pedido-titulo">{{ formaPedido.titulo }}</p>
        <p v-if="formaPedido.detalle" class="det pedido-detalle">{{ formaPedido.detalle }}</p>
        <p v-if="formaPedido.donde" class="det pedido-donde">{{ formaPedido.donde }}</p>
        <div role="status" class="pedido-vivo">
          <p v-if="formaPedido.aviso" class="pedido-aviso">{{ formaPedido.aviso }}</p>
        </div>
        <p v-if="formaPedido.error" class="pedido-error" role="alert">{{ formaPedido.error }}</p>
        <div class="acts" :class="{ 'pedido-envia': formaPedido.enviando }">
          <button
            type="button"
            class="chip rec chip-pedido"
            :class="{ peligro: formaPedido.titulo.startsWith('Cerrar') }"
            :disabled="formaPedido.enviando"
            :aria-label="formaPedido.ariaAceptar"
            @click.stop="emit('pedido', 'aceptar', formaPedido.pedidoId)"
          >{{ formaPedido.boton }}</button>
          <button
            type="button"
            class="chip chip-pedido"
            :disabled="formaPedido.enviando"
            :aria-label="formaPedido.ariaRechazar"
            @click.stop="emit('pedido', 'rechazar', formaPedido.pedidoId)"
          >No</button>
        </div>
      </template>
      <template v-else-if="sesion.estado === 'te-toca' && forma">
        <template v-if="estado?.fase === 'cambio' || estado?.fase === 'error'">
          <p class="warn">{{ estado.mensaje ?? (estado.fase === 'cambio' ? MENSAJE_CAMBIO : '') }}</p>
          <div class="acts">
            <button type="button" class="chip rec" @click.stop="emit('abrir', sesion.session_id)">Abrir en Colmena</button>
          </div>
        </template>
        <template v-else-if="!activa">
          <p>{{ sesion.linea }}</p>
          <div class="acts">
            <button type="button" class="chip" @click.stop="emit('activar', sesion.session_id)">Ver opciones</button>
          </div>
        </template>
        <template v-else>
          <template v-if="forma.tipo === 'cargando'">
            <p class="skel" role="status" aria-label="Cargando">…</p>
          </template>
          <template v-else>
            <p v-if="forma.tipo === 'abrir'">{{ forma.motivo }}</p>
            <p v-else>{{ preguntaDe(forma) }}</p>
            <p v-if="forma.tipo === 'permiso' && forma.detalle" class="det">{{ forma.detalle }}</p>

            <div
              v-if="forma.tipo === 'opciones'"
              class="acts"
              :class="{ apiladas: actsApiladas, 'tras-elegir': trasElegirOpcion && actsApiladas }"
            >
              <button
                v-for="(op, i) in forma.opciones"
                :key="i"
                type="button"
                class="chip"
                :class="{
                  rec: actsApiladas ? i === 0 && opcionElegida === null : i === 0,
                  elegida: actsApiladas && opcionElegida === i,
                }"
                :disabled="bloqueado()"
                @click.stop="clickOpcion(i)"
              >
                <template v-if="actsApiladas">
                  <span class="n" aria-hidden="true">{{ i + 1 }}</span>
                  <span class="lb">{{ op }}</span>
                </template>
                <template v-else>{{ op }}</template>
              </button>
              <div
                v-if="forma.otro && actsApiladas && otroAbierto"
                class="free free-en-fila"
                @click.stop
              >
                <input
                  ref="inputLibre"
                  v-model="textoLibre"
                  type="text"
                  placeholder="Escribí tu respuesta…"
                aria-label="Tu respuesta"
                  :disabled="bloqueado()"
                  @focus="onFocusLibre"
                  @input="onInputLibre"
                  @blur="onBlurLibre"
                  @keydown.enter.prevent="enviarTexto"
                  @keydown.esc.prevent="cerrarOtro"
                />
                <button
                  type="button"
                  class="send send-round"
                  aria-label="Enviar"
                  :disabled="bloqueado() || !textoLibreOk"
                  @click.stop="enviarTexto"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                    <path
                      d="M2 6h7M6.5 3.5 9 6l-2.5 2.5"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="1.6"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                    />
                  </svg>
                </button>
              </div>
              <button
                v-else-if="forma.otro"
                type="button"
                class="chip ghost"
                :disabled="bloqueado()"
                @click.stop="toggleOtro"
              >
                <template v-if="actsApiladas">
                  <span class="n" aria-hidden="true">
                    <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                      <path
                        d="M8.5 1.5l2 2-6.5 6.5H2v-2L8.5 1.5z"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="1.6"
                        stroke-linecap="round"
                        stroke-linejoin="round"
                      />
                    </svg>
                  </span>
                  <span class="lb">Escribir otra respuesta…</span>
                </template>
                <template v-else>Otra cosa…</template>
              </button>
            </div>

            <div
              v-if="forma.tipo === 'opciones' && otroAbierto && !actsApiladas"
              class="free"
              @click.stop
            >
              <input
                ref="inputLibre"
                v-model="textoLibre"
                type="text"
                placeholder="Escribí tu respuesta…"
                aria-label="Tu respuesta"
                :disabled="bloqueado()"
                @focus="onFocusLibre"
                @input="onInputLibre"
                @blur="onBlurLibre"
                @keydown.enter.prevent="enviarTexto"
                @keydown.esc.prevent="cerrarOtro"
              />
              <button
                type="button"
                class="send send-round"
                aria-label="Enviar"
                :disabled="bloqueado() || !textoLibreOk"
                @click.stop="enviarTexto"
              >
                <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
                  <path
                    d="M2 6h7M6.5 3.5 9 6l-2.5 2.5"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="1.6"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
              </button>
            </div>

            <div v-if="forma.tipo === 'permiso'" class="acts">
              <button
                v-if="forma.puedePermitir"
                type="button"
                class="chip rec"
                :disabled="bloqueado()"
                @click.stop="emit('permiso', 'permitir')"
              >
                Permitir
              </button>
              <button type="button" class="chip" :disabled="bloqueado()" @click.stop="emit('permiso', 'rechazar')">Rechazar</button>
            </div>

            <div v-if="forma.tipo === 'abrir'" class="acts">
              <button type="button" class="chip rec" @click.stop="emit('abrir', sesion.session_id)">Abrir en Colmena</button>
            </div>
          </template>
        </template>
      </template>
      <p v-else-if="sesion.linea !== sesion.titulo">{{ sesion.linea }}</p>
    </div>
    <span v-if="sesion.estado !== 'te-toca'" class="t">{{ ago(sesion.last_activity, now) }}</span>
  </div>
</template>

<style scoped>
.row {
  display: grid;
  grid-template-columns: 10px minmax(0, 1fr) auto;
  gap: 2px 10px;
  align-items: start;
  padding: 9px 8px;
  border-radius: var(--r-lg);
  cursor: pointer;
  transition: background 0.2s;
}
.row:hover {
  background: var(--surface);
}
.row.need {
  grid-template-columns: 10px minmax(0, 1fr);
  background: transparent;
  padding: 6px 4px 2px;
  cursor: default;
}
.row.need .main {
  grid-column: 2 / -1;
}
.row.need .acts,
.row.need .free {
  grid-column: 2 / -1;
}
.row.need:hover {
  background: transparent;
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 6px;
  background: var(--c);
  box-shadow: 0 0 8px var(--c);
}
.l1 {
  display: flex;
  align-items: baseline;
  gap: 7px;
  min-width: 0;
}
.l1 strong {
  font-weight: 600;
  font-size: 0.88rem;
}
.row:not(.need) .l1 strong {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row.need .l1 {
  display: block;
  min-width: 0;
}
.row.need .need-head {
  min-width: 0;
}
.row.need .need-title-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.row.need .need-title-row .titulo {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: flex-start;
  gap: 5px;
  font: inherit;
  font-size: 0.875rem;
  font-weight: 600;
  line-height: 1.35;
  color: inherit;
  background: none;
  border: 0;
  padding: 0;
  cursor: pointer;
  text-align: left;
}
.row.need .need-title-row .titulo-text {
  flex: 0 1 auto;
  min-width: 0;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  overflow: hidden;
  white-space: normal;
}
.row.need .need-title-row .titulo-flecha {
  flex: none;
  margin-top: 2px;
  color: var(--text-3);
  opacity: 0;
  transition: opacity 0.15s;
}
.row.need .need-title-row .titulo:hover .titulo-text,
.row.need .need-title-row .titulo:focus-visible .titulo-text {
  text-decoration: underline;
  text-underline-offset: 3px;
  color: var(--text);
}
.row.need .need-title-row .titulo:hover .titulo-flecha,
.row.need .need-title-row .titulo:focus-visible .titulo-flecha {
  opacity: 1;
}
.row.need .need-title-row .titulo:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: 4px;
}
.row.need .when,
.row.need .where {
  font-size: 0.71875rem;
  color: var(--text-3);
  font-weight: 400;
}
.row.need .when {
  flex: none;
  white-space: nowrap;
}
.row.need .where {
  display: block;
  margin-top: 2px;
  line-height: 1.3;
}
.ws,
.t {
  font-family: var(--font-mono);
  font-size: 0.68rem;
  color: var(--text-3);
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
.t {
  padding-top: 2px;
}
.row p {
  margin: 1px 0 0;
  color: var(--text-2);
  font-size: 0.8rem;
}
.row.need p {
  margin-top: 8px;
  font-size: 0.8125rem;
  line-height: 1.45;
  color: var(--text-2);
}
.row:not(.need) p {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.det {
  font-family: var(--font-mono);
  font-size: 0.74rem;
}
.acts {
  grid-column: 2 / 4;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.row.need .acts {
  align-items: center;
  margin-top: 12px;
}
.row.need .acts.apiladas {
  flex-direction: column;
  align-items: stretch;
  gap: 4px;
}
.row.need .acts.apiladas .chip:not(.ghost) {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  column-gap: 10px;
  align-items: center;
  width: 100%;
  box-sizing: border-box;
  min-height: 36px;
  padding: 8px 12px;
  border: 0;
  border-radius: var(--r-md);
  background: color-mix(in srgb, var(--text) 4%, transparent);
  color: var(--text);
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.35;
  white-space: normal;
  text-align: left;
  height: auto;
}
.row.need .acts.apiladas .chip:not(.ghost) .n {
  font-size: 0.6875rem;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
  text-align: center;
  line-height: 1;
}
.row.need .acts.apiladas .chip:not(.ghost) .lb {
  min-width: 0;
}
.row.need .acts.apiladas .chip:not(.ghost):hover:not(:disabled) {
  background: color-mix(in srgb, var(--text) 8%, transparent);
}
.row.need .acts.apiladas .chip:not(.ghost):active:not(:disabled) {
  transform: scale(0.98);
}
.row.need .acts.apiladas .chip:not(.ghost):focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.row.need .acts.apiladas .chip.rec:not(.elegida) {
  background: color-mix(in srgb, var(--accent) 12%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--text);
  font-weight: 500;
}
.row.need .acts.apiladas .chip.rec:not(.elegida) .n {
  color: var(--accent);
}
.row.need .acts.apiladas .chip.rec:not(.elegida):hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 18%, transparent);
}
.row.need .acts.apiladas .chip.elegida {
  background: color-mix(in srgb, var(--accent) 18%, transparent);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
  color: var(--text);
  font-weight: 500;
}
.row.need .acts.apiladas .chip.elegida .n {
  color: var(--accent);
}
.row.need .acts.apiladas.tras-elegir .chip:not(.elegida):not(.ghost) {
  opacity: 0.45;
}
.row.need .acts.apiladas .chip.ghost {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  column-gap: 10px;
  align-items: center;
  width: 100%;
  box-sizing: border-box;
  min-height: 36px;
  padding: 8px 12px;
  margin-left: 0;
  border-radius: var(--r-md);
  border: 1px dashed color-mix(in srgb, var(--text) 14%, transparent);
  background: transparent;
  color: var(--text-3);
  font-size: 0.8125rem;
  font-weight: 500;
  line-height: 1.35;
  text-align: left;
  height: auto;
}
.row.need .acts.apiladas .chip.ghost .n {
  display: flex;
  align-items: center;
  justify-content: center;
  color: inherit;
}
.row.need .acts.apiladas .chip.ghost:hover:not(:disabled) {
  color: var(--text-2);
  border-color: color-mix(in srgb, var(--text) 22%, transparent);
  background: transparent;
  text-decoration: none;
}
.row.need .acts.apiladas .free-en-fila {
  margin-top: 0;
  grid-column: unset;
}
.chip {
  font: inherit;
  font-size: 0.78rem;
  color: var(--text);
  background: transparent;
  border: 1px solid var(--line);
  border-radius: var(--r-pill);
  padding: 5px 12px;
  cursor: pointer;
  transition: background 0.2s, border-color 0.2s, color 0.2s, transform 0.15s;
}
.row.need .chip {
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border-radius: var(--r-pill);
  font-size: 0.78rem;
  font-weight: 500;
  border-color: var(--line-2);
}
.row.need .chip:hover:not(:disabled):not(.rec):not(.ghost) {
  background: var(--surface-2);
}
.chip:hover:not(:disabled):not(.rec):not(.ghost) {
  background: var(--surface-2);
}
.chip:disabled {
  opacity: 0.45;
  cursor: default;
}
.chip.rec {
  font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent);
  border-color: transparent;
}
.row.need .chip.rec {
  font-weight: 600;
  border-color: transparent;
}
.chip.rec:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 88%, white);
}
.chip.ghost {
  background: transparent;
  border: 0;
  border-radius: 0;
  color: var(--text-3);
  padding: 5px 8px;
}
.row.need .chip.ghost {
  margin-left: auto;
  padding: 0 6px;
  height: 32px;
  border: 0;
  border-radius: var(--r-pill);
  font-weight: 500;
}
.chip.ghost:hover:not(:disabled) {
  background: transparent;
  text-decoration: underline;
  color: var(--text-2);
}
.row.need .chip.ghost:hover:not(:disabled) {
  background: transparent;
  text-decoration: none;
  color: var(--text-2);
}
.free {
  grid-column: 2 / 4;
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  min-height: 36px;
  padding: 0 4px 0 12px;
  border-radius: var(--r-md);
  border: 1px solid var(--line-2);
  background: color-mix(in srgb, var(--text) 3%, transparent);
  box-sizing: border-box;
}
.row.need .free {
  margin-top: 12px;
}
.free input {
  flex: 1;
  min-width: 0;
  font: inherit;
  font-size: 0.8125rem;
  color: var(--text);
  background: transparent;
  border: 0;
  padding: 8px 0;
  height: 34px;
  box-sizing: border-box;
}
.free input:focus {
  outline: none;
}
.free input:disabled {
  opacity: 0.45;
}
.send {
  font: inherit;
  font-size: 0.78rem;
  font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent);
  border: 0;
  border-radius: var(--r-md);
  padding: 5px 12px;
  cursor: pointer;
  flex: none;
}
.send.send-round {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border-radius: 50%;
  margin-right: 4px;
}
.send:hover:not(:disabled) {
  background: color-mix(in srgb, var(--accent) 88%, white);
}
.send:disabled {
  opacity: 0.45;
  cursor: default;
}
.sent {
  color: var(--accent) !important;
  font-size: 0.78rem !important;
}
.warn {
  color: var(--st-blocked) !important;
}
.skel {
  opacity: 0.35;
}
.row.need p.pedido-titulo {
  margin-top: 8px;
  font-weight: 600;
  color: var(--text);
}
.row.need p.pedido-detalle {
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pedido-vivo {
  display: contents;
}
.row.need p.pedido-donde {
  margin-top: 2px;
  font-family: var(--font-mono);
  font-size: 0.72rem;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.row.need p.pedido-aviso {
  margin-top: 8px;
  padding: 6px 10px;
  border-radius: var(--r-md);
  font-size: 0.75rem;
  color: var(--st-working);
  background: var(--st-working-soft);
}
.row.need p.pedido-error {
  margin-top: 8px;
  font-size: 0.75rem;
  color: var(--danger);
}
.chip-pedido {
  position: relative;
  transition: opacity 0.2s, transform 0.15s;
}
.chip-pedido::after {
  content: '';
  position: absolute;
  inset: -6px -2px;
}
.chip-pedido:active:not(:disabled) {
  transform: scale(0.97);
}
/* .row.need .chip.rec pisa a .chip.rec: hace falta la regla con más especificidad */
.row.need .chip.rec.peligro {
  background: var(--danger);
  color: var(--danger-ink);
}
@media (hover: hover) and (pointer: fine) {
  .chip.rec.peligro:hover:not(:disabled) {
    background: color-mix(in srgb, var(--danger) 88%, white);
  }
}
@media (prefers-reduced-motion: reduce) {
  .chip-pedido {
    transition: opacity 0.2s;
  }
  .chip-pedido:active:not(:disabled) {
    transform: none;
  }
}
</style>
