<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import {
  abrirSesionDesdeAvisoSimple,
  crearControlCierreDone,
  DURACION_TERMINO_S,
  esPedidoPestanaNotch,
  esTeTocaAviso,
  nombreAviso,
  type AvisoNotch,
  type ControlCierreDone,
  type TweenCierreDone,
} from '../../lib/notchAvisos'
import {
  abrirPedidoPestana,
  pedidoPestanaPorId,
  pedidosPestana,
  rechazarPedidoPestana,
} from '../../state/pedidosPestana'
import { cerrarAviso } from '../../state/notchAvisos'
import PedidoPestanaCard from '../PedidoPestanaCard.vue'
import type { SesionNotch } from '../../lib/notchCeldas'
import { gsap, isSoft, useGsap } from '../../motion'
import {
  activa,
  activar,
  elegirOpcion,
  filas,
  formaDe,
  mandarTexto,
  resolverPedido,
  resolverPermiso,
} from '../../state/notchRespuesta'
import { iconoAviso } from '../../lib/avisos'
import { piezas } from '../../piezas'
import { esCampoTextoNotch } from '../../lib/notchTeclado'
import Icon from '../Icon.vue'
import NotchFila from './NotchFila.vue'

const { aviso, sesion, now } = defineProps<{
  aviso: AvisoNotch
  sesion: SesionNotch | null
  now: number
}>()

const emit = defineEmits<{ cerrar: []; 'abrir-sesion': [sid: string] }>()
const avisosDePiezas = piezas().flatMap((p) => (p.avisos ? [p.avisos] : []))

const root = ref<HTMLElement | null>(null)
const bar = ref<SVGCircleElement | null>(null)
const ico = ref<HTMLElement | null>(null)
const { run } = useGsap()

const conFila = computed(() => esTeTocaAviso(aviso) && !esPedidoPestanaNotch(aviso) && !!sesion)
const esPestana = computed(() => esPedidoPestanaNotch(aviso))
const pedidoPestana = computed(() => (aviso.pedido ? pedidoPestanaPorId(aviso.pedido) : undefined))
const nombre = computed(() => nombreAviso(aviso.titulo, aviso.kind))

async function onAbrirPestana(id: string) {
  await abrirPedidoPestana(id)
  cerrarAviso()
}

async function onRechazarPestana(id: string) {
  await rechazarPedidoPestana(id)
  cerrarAviso()
}

let cerrado = false
let controlCierre: ControlCierreDone | null = null

function emitCerrarOnce() {
  if (cerrado) return
  cerrado = true
  controlCierre?.dispose()
  controlCierre = null
  emit('cerrar')
}

onMounted(() => {
  run(() => {
    if (aviso.kind === 'done') {
      const soft = isSoft()
      controlCierre = crearControlCierreDone({
        duracionMs: DURACION_TERMINO_S * 1000,
        margenTimeoutMs: soft ? 0 : 100,
        now: () => Date.now(),
        onCerrar: () => emitCerrarOnce(),
        schedule: (fn, ms) => setTimeout(fn, ms),
        cancel: (id) => {
          if (id != null) clearTimeout(id)
        },
        crearTween: soft
          ? undefined
          : () => {
              if (!bar.value) return null
              return gsap.fromTo(
                bar.value,
                { strokeDashoffset: 0 },
                {
                  strokeDashoffset: 1,
                  duration: DURACION_TERMINO_S,
                  ease: 'none',
                  onComplete: () => emitCerrarOnce(),
                },
              ) as unknown as TweenCierreDone
            },
      })
    }
    if (ico.value && !isSoft()) {
      gsap.fromTo(
        ico.value,
        { scale: 0.6, opacity: 0 },
        { scale: 1, opacity: 1, duration: 0.5, delay: 0.15, ease: 'back.out(2.2)' },
      )
    }
  })
})

onBeforeUnmount(() => {
  if (root.value) gsap.killTweensOf(root.value)
  controlCierre?.dispose()
  controlCierre = null
})

function onCerrar() {
  emitCerrarOnce()
}

function onMainAbrir() {
  const sid = abrirSesionDesdeAvisoSimple(aviso.session_id)
  if (sid) emit('abrir-sesion', sid)
}

function onMainKey(e: KeyboardEvent) {
  if (e.key !== 'Enter' && e.key !== ' ') return
  if (esCampoTextoNotch(e.target)) return
  e.preventDefault()
  onMainAbrir()
}

function onToastEnter() {
  if (aviso.kind === 'done') controlCierre?.pointerEnter()
}

function onToastLeave() {
  if (aviso.kind === 'done') controlCierre?.pointerLeave()
}

function onOpcion(i: number) {
  if (sesion) elegirOpcion(sesion, i)
}

function onTexto(t: string) {
  if (sesion) mandarTexto(sesion, t)
}

function onPermiso(a: 'permitir' | 'rechazar') {
  if (sesion) resolverPermiso(sesion, a)
}

function onPedido(a: 'aceptar' | 'rechazar', pedidoId: string) {
  if (sesion) resolverPedido(sesion, a, pedidoId)
}

function onAbrir(sid: string) {
  emit('abrir-sesion', sid)
}
</script>

<template>
  <div
    ref="root"
    class="toast"
    :class="[`k-${aviso.kind}`, { simple: !conFila && !esPestana, pestana: esPestana }]"
    role="status"
    aria-atomic="true"
    @click.stop
    @mouseenter="onToastEnter"
    @mouseleave="onToastLeave"
  >
    <PedidoPestanaCard
      v-if="esPestana && pedidoPestana"
      :pedido="pedidoPestana"
      notch
      compact
      :busy="!!(aviso.pedido && pedidosPestana.porId[aviso.pedido]?.enviando)"
      :error="aviso.pedido ? pedidosPestana.porId[aviso.pedido]?.error : ''"
      :vista="aviso.pedido ? pedidosPestana.porId[aviso.pedido]?.vista : undefined"
      @abrir="onAbrirPestana"
      @rechazar="onRechazarPestana"
    />
    <NotchFila
      v-else-if="conFila && sesion"
      :sesion="sesion"
      :now="now"
      :forma="formaDe(sesion)"
      :estado="filas[sesion.session_id]"
      :activa="activa === sesion.session_id"
      @activar="activar"
      @abrir="onAbrir"
      @opcion="onOpcion"
      @texto="onTexto"
      @permiso="onPermiso"
      @pedido="onPedido"
    />
    <template v-else>
      <span ref="ico" class="ico" aria-hidden="true">
        <Icon :name="iconoAviso(aviso.kind, avisosDePiezas)" :size="18" />
      </span>
      <div
        class="main"
        role="button"
        tabindex="0"
        aria-label="Abrir sesión"
        @click="onMainAbrir"
        @keydown="onMainKey"
      >
        <div class="l1">
          <strong class="nombre">{{ nombre }}</strong>
          <svg
            class="flecha"
            width="11"
            height="11"
            viewBox="0 0 11 11"
            aria-hidden="true"
          >
            <path
              d="M4.5 1.5h5v5M9.5 1.5L2 9"
              fill="none"
              stroke="currentColor"
              stroke-width="1.6"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <span class="when">ahora</span>
        </div>
        <p>{{ aviso.cuerpo }}</p>
      </div>
    </template>
    <button type="button" class="x" aria-label="Cerrar aviso" @click.stop="onCerrar">
      <svg width="12" height="12" viewBox="0 0 12 12" aria-hidden="true">
        <path
          d="M3 3l6 6M9 3L3 9"
          fill="none"
          stroke="currentColor"
          stroke-width="1.6"
          stroke-linecap="round"
        />
      </svg>
    </button>
    <svg
      v-if="aviso.kind === 'done'"
      class="prog"
      width="44"
      height="44"
      viewBox="0 0 44 44"
      aria-hidden="true"
    >
      <circle class="track" cx="22" cy="22" r="21" />
      <circle ref="bar" class="ind" cx="22" cy="22" r="21" pathLength="1" />
    </svg>
  </div>
</template>

<style scoped>
.toast {
  --k: var(--st-done);
  position: relative;
  isolation: isolate;
  display: grid;
  align-items: start;
}
.toast.k-asks {
  --k: var(--st-working);
}
.toast.k-blocked {
  --k: var(--st-blocked);
}
.toast.simple {
  grid-template-columns: 44px minmax(0, 1fr) 28px;
  column-gap: 12px;
  padding: 10px 4px 0 2px;
}
.ico {
  grid-area: 1 / 1;
  justify-self: center;
  margin-top: 4px;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--k);
  background: radial-gradient(
    circle at 50% 30%,
    color-mix(in srgb, var(--k) 26%, transparent),
    color-mix(in srgb, var(--k) 10%, transparent) 70%
  );
  box-shadow:
    inset 0 0 0 1px color-mix(in srgb, var(--k) 30%, transparent),
    0 0 20px -6px color-mix(in srgb, var(--k) 55%, transparent);
}
.prog {
  grid-area: 1 / 1;
  justify-self: center;
  align-self: start;
  width: 44px;
  height: 44px;
  transform: rotate(-90deg);
  overflow: visible;
  pointer-events: none;
}
.prog .track {
  fill: none;
  stroke: color-mix(in srgb, var(--k) 16%, transparent);
  stroke-width: 2;
}
.prog .ind {
  fill: none;
  stroke: var(--k);
  stroke-width: 2;
  stroke-linecap: round;
  stroke-dasharray: 1;
  stroke-dashoffset: 0;
  filter: drop-shadow(0 0 3px color-mix(in srgb, var(--k) 60%, transparent));
  transition: stroke-opacity 0.2s;
}
.toast:hover .prog .ind {
  stroke-opacity: 0.55;
}
.main {
  grid-area: 1 / 2;
  min-width: 0;
  cursor: pointer;
  border-radius: var(--r-md);
}
.main:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 3px;
}
.l1 {
  display: flex;
  align-items: baseline;
  gap: 6px;
  min-width: 0;
  min-height: 24px;
  padding-top: 2px;
}
.nombre {
  flex: 0 1 auto;
  min-width: 0;
  font-family: var(--font-display);
  font-size: 0.9375rem;
  font-weight: 600;
  letter-spacing: -0.01em;
  line-height: 1.3;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.flecha {
  flex: none;
  align-self: center;
  color: var(--text-3);
  opacity: 0;
  transform: translateX(-2px);
  transition:
    opacity 0.15s,
    transform 0.15s var(--ease-out);
}
.main:hover .flecha,
.main:focus-visible .flecha {
  opacity: 1;
  transform: none;
}
.when {
  margin-left: auto;
  flex: none;
  font-size: 0.71875rem;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.main p {
  margin: 3px 0 0;
  font-size: 0.8125rem;
  line-height: 1.45;
  color: var(--text-2);
  text-wrap: pretty;
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 3;
  overflow: hidden;
}
.x {
  grid-area: 1 / 3;
  align-self: start;
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: var(--r-pill);
  color: var(--text-3);
  background: transparent;
  cursor: pointer;
  transition:
    background 0.15s,
    color 0.15s,
    transform 0.1s;
}
.x:hover {
  color: var(--text);
  background: color-mix(in srgb, var(--text) 8%, transparent);
}
.x:active {
  transform: scale(var(--press-scale));
}
.x:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 1px;
}
.toast:not(.simple) {
  grid-template-columns: minmax(0, 1fr) 28px;
  column-gap: 4px;
  padding: 8px 2px 0 0;
}
.toast:not(.simple) :deep(.row) {
  grid-area: 1 / 1;
}
.toast:not(.simple) .x {
  grid-area: 1 / 2;
  margin-top: 4px;
}
.toast.pestana {
  grid-template-columns: minmax(0, 1fr) 28px;
  column-gap: 8px;
  padding: 6px 2px 0 0;
}
.toast.pestana :deep(.ppc) {
  grid-area: 1 / 1;
  min-width: 0;
}
.toast.pestana .x {
  grid-area: 1 / 2;
  align-self: start;
  margin-top: 2px;
}
</style>
