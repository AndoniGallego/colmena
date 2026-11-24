<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { PuertoEntorno } from '../api/entornosApi'
import { desktop } from '../lib/viewport'
import type { Entorno } from '../api/entornosApi'
import {
  ariaSalud,
  conEnlace,
  explicarError,
  faseDe,
  lineaServicioProblema,
  resumenEntornos,
  serviciosConProblema,
  type EstadoVista,
  type FaseTunel,
} from '../lib/entornos'
import { SOLO_APP } from '../lib/entornosPuente'
import type { EstadoTunel } from '../lib/entornosPuente'
import { animateViewEnter, gsap, isSoft, useGsap } from '../motion'
import {
  abrirEntorno,
  abrirPuerto,
  entornos,
  cargarEntornos,
  cerrarEntorno,
  cambiarNotebook,
  closeEntornos,
  refrescarTuneles,
} from '../state/entornos'
import { useFocusTrap } from '../lib/focusTrap'
import Icon from './Icon.vue'
import InlineAlert from './InlineAlert.vue'
import EntornosProbador from './EntornosProbador.vue'
import ViewFrame from './ViewFrame.vue'

const { run } = useGsap()
const gridRef = ref<HTMLElement | null>(null)
const frame = ref<{ $el: HTMLElement } | null>(null)
const panel = computed(() => frame.value?.$el ?? null)
const backBtn = ref<HTMLButtonElement | null>(null)
const { onKeydown: trapKeydown } = useFocusTrap(panel, () => true, {
  onEscape: closeEntornos,
  initial: () => backBtn.value,
})

const estadoVista = computed<EstadoVista>(() => ({
  tuneles: entornos.tuneles,
  abriendo: entornos.abriendo,
  errores: entornos.errores,
}))

const listaActivos = computed(() => entornos.lista.filter((e) => !e.apagado))
const listaApagados = computed(() => entornos.lista.filter((e) => e.apagado))

const resumen = computed(() =>
  resumenEntornos(
    listaActivos.value.map((e) => e.nombre),
    estadoVista.value,
  ),
)

const probando = ref<string | null>(null)

function tienePuertoAbrible(e: Entorno): boolean {
  return e.puertos.some((p) => p.abrible)
}

function abrirProbador(e: Entorno) {
  probando.value = e.nombre
}

function problemasDe(e: Entorno) {
  return serviciosConProblema(e.servicios)
}

const faseBarra = computed<FaseTunel>(() => {
  if (entornos.error) return 'error'
  if (entornos.cargando) return 'abriendo'
  return 'abierto'
})

function tunelDe(nombre: string): EstadoTunel | undefined {
  return entornos.tuneles[nombre]
}

function vistaCard(nombre: string) {
  return faseDe(nombre, estadoVista.value)
}

function explicado(nombre: string) {
  const err = vistaCard(nombre).error || ''
  return explicarError(err)
}

function etiquetaFase(f: FaseTunel): string {
  if (f === 'cerrado') return 'Cerrado'
  if (f === 'abriendo') return 'Conectando…'
  if (f === 'abierto') return 'Abierto'
  return 'Falló'
}

function onWinFocus() {
  void refrescarTuneles()
}

async function animarEntrada() {
  await nextTick()
  animateViewEnter(gsap, run, gridRef.value?.querySelectorAll('.en-card'), isSoft(), {
    y: 14,
    duration: 0.5,
    stagger: 0.06,
  })
}

watch(
  () => entornos.lista.length,
  (n, prev) => {
    if (n > 0 && prev === 0) void animarEntrada()
  },
)

onMounted(() => {
  window.addEventListener('focus', onWinFocus)
  if (entornos.lista.length > 0) void animarEntrada()
  void cargarEntornos()
})

onBeforeUnmount(() => {
  window.removeEventListener('focus', onWinFocus)
})
</script>

<template>
  <ViewFrame
    ref="frame"
    class="en"
    :class="{ desk: desktop }"
    role="dialog"
    aria-modal="true"
    aria-label="Entornos"
    tabindex="-1"
    title="Entornos"
    sticky-head
    show-back
    :back-icon="desktop ? 'close' : 'back'"
    :back-label="desktop ? 'Cerrar Entornos' : 'Volver'"
    @back="closeEntornos"
    @keydown="trapKeydown"
  >
    <template #back>
      <button ref="backBtn" type="button" class="btn btn-back btn-icon" :class="{ 'btn-back--wide': desktop }" :aria-label="desktop ? 'Cerrar Entornos' : 'Volver'" @click="closeEntornos">
        <Icon :name="desktop ? 'close' : 'back'" :size="18" />
        <span v-if="desktop" class="esc mono">Esc</span>
      </button>
    </template>

    <div class="en-body">
      <div class="en-bar ui-card">
        <div class="en-bar-main">
          <template v-if="entornos.enPrograma">
            <span class="en-luz" aria-hidden="true" :data-fase="faseBarra" />
            <span class="en-lab">Notebook</span>
            <code v-if="entornos.notebook">{{ entornos.notebook }}</code>
            <span v-else class="en-sin-notebook">Configurá la notebook</span>
            <button type="button" class="btn btn-ghost en-cambiar" @click="cambiarNotebook">cambiar</button>
          </template>
          <p v-else class="en-solo">{{ SOLO_APP }}</p>
        </div>
        <div class="en-bar-side">
          <span v-if="resumen.texto" class="en-resumen">{{ resumen.texto }}</span>
          <button
            type="button"
            class="btn btn-icon"
            aria-label="Actualizar"
            :disabled="entornos.cargando"
            @click="cargarEntornos()"
          >
            <Icon name="refresh" :class="{ girando: entornos.cargando }" :size="18" />
          </button>
        </div>
      </div>

      <InlineAlert v-if="entornos.error" :detalle="entornos.errorDetalle">{{ entornos.error }}</InlineAlert>

      <template v-if="entornos.cargando && entornos.lista.length === 0">
        <p class="sr-only">Buscando entornos…</p>
        <div v-for="n in 3" :key="n" class="en-skel" aria-hidden="true" />
      </template>

      <div
        v-else-if="!entornos.cargando && !entornos.error && listaActivos.length === 0 && listaApagados.length === 0"
        class="en-vacio"
      >
        <Icon name="monitor" :size="32" />
        <p>No hay entornos corriendo en la notebook</p>
      </div>

      <div v-else class="en-main">
      <div ref="gridRef" class="en-grid">
        <article
          v-for="e in listaActivos"
          :key="e.nombre"
          class="en-card ui-card"
          :data-fase="vistaCard(e.nombre).fase"
        >
          <header class="en-head">
            <span class="en-luz" aria-hidden="true" :data-fase="vistaCard(e.nombre).fase" />
            <span
              v-if="e.salud"
              class="en-salud"
              role="img"
              :data-salud="e.salud"
              :aria-label="ariaSalud(e.salud) ?? undefined"
            />
            <div class="en-head-main">
              <h2 class="en-nombre">{{ e.nombre }}</h2>
              <p class="en-carpeta mono" :title="e.carpeta">{{ e.carpeta }}</p>
            </div>
            <span class="en-tag">{{ etiquetaFase(vistaCard(e.nombre).fase) }}</span>
          </header>

          <ul v-if="problemasDe(e).length" class="en-svc-prob">
            <li v-for="s in problemasDe(e)" :key="`${e.nombre}-${s.servicio}-${s.estado}`">{{ lineaServicioProblema(s) }}</li>
          </ul>

          <div v-if="vistaCard(e.nombre).fase === 'error'" class="en-falla" role="alert">
            <span>{{ explicado(e.nombre).texto }}</span>
            <details v-if="explicado(e.nombre).original" class="en-detalle">
              <summary>Ver detalle</summary>
              <pre>{{ explicado(e.nombre).original }}</pre>
            </details>
          </div>

          <ul class="en-chips">
            <li v-for="(p, i) in e.puertos" :key="p.puerto">
              <button
                v-if="conEnlace(p as PuertoEntorno, vistaCard(e.nombre), tunelDe(e.nombre))"
                type="button"
                class="en-chip on"
                :style="{ '--i': i }"
                :data-principal="p.puerto === e.principal ? '' : undefined"
                :aria-label="`Abrir ${p.servicio} en el navegador`"
                @click="abrirPuerto(e, p.puerto)"
              >
                <span class="en-svc">{{ p.servicio }}</span>
                <span class="en-port mono">:{{ p.puerto }}</span>
                <Icon name="external" :size="12" />
              </button>
              <span
                v-else
                class="en-chip"
                :data-principal="p.puerto === e.principal ? '' : undefined"
              >
                <span class="en-svc">{{ p.servicio }}</span>
                <span class="en-port mono">:{{ p.puerto }}</span>
              </span>
            </li>
          </ul>

          <div v-if="tienePuertoAbrible(e) || entornos.enPrograma" class="en-actions">
            <button
              v-if="tienePuertoAbrible(e)"
              type="button"
              class="btn btn-ghost"
              @click="abrirProbador(e)"
            >
              Probar
            </button>
            <template v-if="entornos.enPrograma">
              <button
                v-if="vistaCard(e.nombre).fase === 'abierto'"
                type="button"
                class="btn btn-danger-soft"
                :disabled="entornos.cerrando.includes(e.nombre)"
                @click="cerrarEntorno(e.nombre)"
              >
                {{ entornos.cerrando.includes(e.nombre) ? 'Desconectando…' : 'Desconectar' }}
              </button>
              <button
                v-else
                type="button"
                class="btn btn-primary"
                :disabled="e.principal === null || entornos.abriendo.includes(e.nombre)"
                @click="abrirEntorno(e)"
              >
                <Icon name="play" :size="14" />
                {{ entornos.abriendo.includes(e.nombre) ? 'Conectando…' : 'Conectar' }}
              </button>
            </template>
          </div>
          <EntornosProbador
            v-if="probando === e.nombre"
            :entorno="e"
            @cerrar="probando = null"
          />
        </article>
      </div>

      <details v-if="listaApagados.length" class="en-apagados">
        <summary>Apagados ({{ listaApagados.length }})</summary>
        <div class="en-apagados-grid">
          <article v-for="e in listaApagados" :key="e.nombre" class="en-card ui-card en-card--apagado">
            <header class="en-head en-head--simple">
              <span
                v-if="e.salud"
                class="en-salud"
                role="img"
                :data-salud="e.salud"
                :aria-label="ariaSalud(e.salud) ?? undefined"
              />
              <h2 class="en-nombre">{{ e.nombre }}</h2>
            </header>
            <ul v-if="problemasDe(e).length" class="en-svc-prob">
              <li v-for="s in problemasDe(e)" :key="`${e.nombre}-${s.servicio}-${s.estado}`">{{ lineaServicioProblema(s) }}</li>
            </ul>
          </article>
        </div>
      </details>
      </div>
    </div>
  </ViewFrame>
</template>

<style scoped>
.en {
  position: fixed;
  inset: 0;
  z-index: 80;
  background-image: radial-gradient(1000px 420px at 0% -10%, var(--accent-soft), transparent 60%);
  outline: none;
  overflow: hidden;
}
.en :deep(.vf-body) {
  flex: 1;
  min-height: 0;
  padding: 0;
  gap: 0;
  overflow: hidden;
}
.esc {
  font-size: var(--t-xs);
  color: var(--text-4);
  padding: 2px 5px;
  border-radius: 5px;
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.en-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--view-pad-top) var(--gutter) calc(40px + env(safe-area-inset-bottom));
  padding-left: max(var(--gutter), env(safe-area-inset-left));
  padding-right: max(var(--gutter), env(safe-area-inset-right));
  display: grid;
  gap: 16px;
  max-width: var(--read-max);
  width: 100%;
  margin: 0 auto;
  align-content: start;
}
.desk .en-body {
  max-width: none;
  padding-top: 28px;
}
.en-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px 16px;
  padding: 12px 14px;
}
.en-bar-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  font-size: 14px;
  min-width: 0;
}
.en-bar-side {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}
.en-lab {
  font-weight: 540;
}
.en-bar-main code {
  font-size: 13px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line);
}
.en-solo {
  margin: 0;
  font-size: 14px;
  color: var(--text-2);
  line-height: 1.45;
}
.en-resumen {
  font-size: 13px;
  color: var(--text-3);
  white-space: nowrap;
}
.en-luz {
  flex-shrink: 0;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: var(--text-4);
}
.en-luz[data-fase='abierto'] {
  background: var(--st-done);
  box-shadow:
    0 0 0 4px color-mix(in srgb, var(--st-done) 22%, transparent),
    0 0 10px color-mix(in srgb, var(--st-done) 45%, transparent);
}
.en-luz[data-fase='abriendo'] {
  position: relative;
  background: var(--st-working);
  animation: en-pulse 1.1s var(--ease-out) infinite;
}
.en-luz[data-fase='abriendo']::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--st-working);
  pointer-events: none;
  animation: en-pulse-halo 1.1s var(--ease-out) infinite;
}
.en-luz[data-fase='error'] {
  background: var(--danger);
}
.en-luz[data-fase='cerrado'] {
  background: var(--text-4);
}
.en-vacio {
  display: grid;
  justify-items: center;
  gap: 12px;
  padding: 32px 16px;
  text-align: center;
  color: var(--text-3);
  font-size: 14px;
}
.en-vacio p {
  margin: 0;
}
.en-skel {
  height: 140px;
  border-radius: var(--r-card);
  --sk-bg: linear-gradient(
    90deg,
    var(--surface-2) 0%,
    color-mix(in srgb, var(--surface) 40%, var(--surface-2)) 50%,
    var(--surface-2) 100%
  );
  position: relative;
  overflow: hidden;
  isolation: isolate;
}
.en-skel::after {
  content: '';
  position: absolute;
  top: 0;
  bottom: 0;
  left: -400%;
  width: 600%;
  z-index: -1;
  pointer-events: none;
  background: var(--sk-bg);
  background-size: 33.3333% 100%;
  animation: sk-slide 1.3s linear infinite;
  --sk-dx: 66.6667%;
}
.en-grid {
  display: grid;
  gap: 14px;
  grid-template-columns: minmax(0, 1fr);
}
.desk .en-grid {
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
}
.en-card {
  position: relative;
  overflow: hidden;
  padding: 16px 18px;
  display: grid;
  gap: 12px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  transition:
    border-color 200ms var(--ease-out),
    background 200ms var(--ease-out),
    box-shadow 200ms var(--ease-out);
}
.en-card[data-fase='abierto'] {
  animation: en-glow 900ms var(--ease-out) 1;
}
.en-card[data-fase='abriendo']::before {
  content: '';
  position: absolute;
  top: 0;
  left: -400%;
  width: 600%;
  height: 2px;
  background: linear-gradient(
    90deg,
    transparent,
    var(--accent) 45%,
    color-mix(in srgb, var(--accent) 60%, white) 55%,
    transparent
  );
  background-size: 33.3333% 100%;
  animation: en-sweep 1.4s linear infinite;
  pointer-events: none;
}
@media (hover: hover) {
  .en-card:hover {
    box-shadow:
      inset 0 0 0 1px var(--line-2),
      0 6px 20px color-mix(in srgb, var(--text) 8%, transparent);
  }
}
.en-main {
  display: grid;
  gap: 14px;
}
.en-salud {
  flex-shrink: 0;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  align-self: center;
}
.en-salud[data-salud='verde'] {
  background: var(--st-done);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--st-done) 22%, transparent);
}
.en-salud[data-salud='amarillo'] {
  background: var(--st-blocked);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--st-blocked) 22%, transparent);
}
.en-salud[data-salud='rojo'] {
  background: var(--danger);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--danger) 22%, transparent);
}
.en-svc-prob {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--text-2);
  line-height: 1.35;
}
.en-apagados summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 540;
  color: var(--text-2);
  margin-bottom: 10px;
}
.en-apagados-grid {
  display: grid;
  gap: 10px;
}
.en-card--apagado {
  opacity: 0.92;
}
.en-head--simple {
  grid-template-columns: auto 1fr;
  align-items: center;
}
.en-head {
  display: grid;
  grid-template-columns: auto auto 1fr auto;
  align-items: start;
  gap: 10px;
}
.en-head-main {
  min-width: 0;
}
.en-nombre {
  margin: 0;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 620;
  line-height: 1.25;
}
.en-carpeta {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.en-tag {
  font-size: 12px;
  font-weight: 560;
  padding: 3px 10px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line);
  white-space: nowrap;
}
.en-card[data-fase='abierto'] .en-tag {
  color: var(--st-done);
  background: color-mix(in srgb, var(--st-done) 10%, var(--surface));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--st-done) 28%, var(--line));
}
.en-card[data-fase='abriendo'] .en-tag {
  color: var(--st-working);
}
.en-card[data-fase='error'] .en-tag {
  color: var(--danger);
}
.en-falla {
  font-size: 13px;
  color: var(--danger);
  line-height: 1.45;
  padding: 10px 12px;
  border-radius: var(--r-md);
  background: color-mix(in srgb, var(--danger) 8%, var(--surface));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 22%, var(--line));
}
.en-detalle {
  margin-top: 8px;
}
.en-detalle summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 540;
  color: var(--text-2);
}
.en-detalle pre {
  margin: 8px 0 0;
  font-size: var(--t-sm);
  color: var(--text-3);
  white-space: pre-wrap;
  word-break: break-word;
}
.en-chips {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.en-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--t-md);
  padding: 6px 10px;
  border-radius: var(--r-pill);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line);
  color: var(--text-2);
}
.en-chip[data-principal] {
  box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 55%, var(--line));
  background: color-mix(in srgb, var(--accent-soft) 70%, var(--surface-2));
}
.en-chip.on {
  cursor: pointer;
  border: none;
  font: inherit;
  color: var(--text);
  animation: en-pop 380ms var(--spring) both;
  animation-delay: calc(var(--i, 0) * 60ms);
}
@media (hover: hover) {
  .en-chip.on:hover {
    transform: translateY(-1px);
    box-shadow:
      inset 0 0 0 1px var(--accent),
      0 4px 12px color-mix(in srgb, var(--accent) 18%, transparent);
  }
}
.en-svc {
  font-weight: 540;
}
.en-port {
  color: var(--text-3);
  font-size: 12px;
}
.en-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.en-actions .btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

@keyframes en-pulse {
  0%,
  100% {
    transform: scale(1);
  }
  50% {
    transform: scale(1.08);
  }
}
@keyframes en-pulse-halo {
  0%,
  100% {
    transform: scale(1);
    opacity: 0.25;
  }
  50% {
    transform: scale(2.1111);
    opacity: 0.12;
  }
}
@keyframes en-sweep {
  to {
    transform: translateX(66.6667%);
  }
}
@keyframes en-glow {
  0% {
    box-shadow:
      inset 0 0 0 1px var(--line),
      0 0 0 0 color-mix(in srgb, var(--st-done) 35%, transparent);
  }
  40% {
    box-shadow:
      inset 0 0 0 1px color-mix(in srgb, var(--st-done) 40%, var(--line)),
      0 0 24px color-mix(in srgb, var(--st-done) 30%, transparent);
  }
  100% {
    box-shadow: inset 0 0 0 1px var(--line);
  }
}
@keyframes en-pop {
  from {
    opacity: 0;
    transform: scale(0.92);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}

.girando {
  animation: en-giro 0.9s linear infinite;
}
@keyframes en-giro {
  to {
    transform: rotate(360deg);
  }
}

:root[data-motion='soft'] .en-luz[data-fase='abriendo'],
:root[data-motion='soft'] .en-card[data-fase='abriendo']::before,
:root[data-motion='soft'] .en-card[data-fase='abierto'],
:root[data-motion='soft'] .en-chip.on,
:root[data-motion='soft'] .en-skel::after,
:root[data-motion='soft'] .en-luz[data-fase='abriendo']::after,
:root[data-motion='soft'] .girando {
  animation: none;
}
@media (prefers-reduced-motion: reduce) {
  .en-luz[data-fase='abriendo'],
  .en-luz[data-fase='abriendo']::after,
  .en-card[data-fase='abriendo']::before,
  .en-card[data-fase='abierto'],
  .en-chip.on,
  .en-skel::after,
  .girando {
    animation: none;
  }
}
</style>
