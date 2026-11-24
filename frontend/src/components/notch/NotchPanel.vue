<script setup lang="ts">
import { nextTick, ref, watch } from 'vue'
import type { Grupos, SesionNotch } from '../../lib/notchCeldas'
import { cascadeDelay, gsap, isSoft, useGsap } from '../../motion'
import { activa, activar, elegirOpcion, filas, formaDe, mandarTexto, resolverPedido, resolverPermiso } from '../../state/notchRespuesta'
import NotchFila from './NotchFila.vue'
import NotchNotas from './NotchNotas.vue'

const props = withDefaults(
  defineProps<{ grupos: Grupos; now: number; initialOtrasDesplegadas?: boolean; reunionDisponible?: boolean }>(),
  { initialOtrasDesplegadas: false, reunionDisponible: false },
)
const emit = defineEmits<{ 'abrir-sesion': [sid: string]; 'abrir-colmena': []; 'abrir-reunion': [] }>()

const otrasDesplegadas = ref(props.initialOtrasDesplegadas)
const otrasRoot = ref<HTMLElement | null>(null)
const { run } = useGsap()

const orden = [
  { key: 'teToca' as const, label: 'Te toca' },
  { key: 'trabajando' as const, label: 'Trabajando' },
  { key: 'termino' as const, label: 'Terminó' },
]

function toggleOtras() {
  otrasDesplegadas.value = !otrasDesplegadas.value
}

function animarOtras() {
  const el = otrasRoot.value
  if (!el) return
  const filasEl = el.querySelectorAll<HTMLElement>('.row')
  if (!filasEl.length) return
  if (isSoft()) return void run(() => gsap.from(filasEl, { opacity: 0, duration: 0.25 }))
  run(() =>
    gsap.from(filasEl, {
      y: 8,
      opacity: 0,
      duration: 0.45,
      ease: 'power3.out',
      stagger: 0.04,
      delay: cascadeDelay(0.04, 8),
      clearProps: 'transform,opacity',
    }),
  )
}

watch(otrasDesplegadas, async (abierto) => {
  if (!abierto) return
  await nextTick()
  animarOtras()
})

function filaGrupo(s: SesionNotch, teToca: boolean) {
  return {
    sesion: s,
    now: props.now,
    forma: teToca ? formaDe(s) : undefined,
    estado: filas[s.session_id],
    activa: activa.value === s.session_id,
  }
}
</script>

<template>
  <div class="panel">
    <template v-for="g in orden" :key="g.key">
      <template v-if="grupos[g.key].length">
        <p class="grp">{{ g.label }}</p>
        <NotchFila
          v-for="s in grupos[g.key]"
          :key="s.pane_id"
          v-bind="filaGrupo(s, g.key === 'teToca')"
          @abrir="emit('abrir-sesion', $event)"
          @activar="(sid) => activar(sid, s)"
          @opcion="(i) => elegirOpcion(s, i)"
          @texto="(t) => mandarTexto(s, t)"
          @permiso="(a) => resolverPermiso(s, a)"
          @pedido="(a, id) => resolverPedido(s, a, id)"
        />
      </template>
    </template>
    <button
      v-if="grupos.otras.length"
      type="button"
      class="mas"
      :aria-expanded="otrasDesplegadas"
      @click="toggleOtras"
    >
      {{
        otrasDesplegadas
          ? 'Ocultar'
          : grupos.otras.length === 1
            ? 'Ver 1 sesión más'
            : `Ver ${grupos.otras.length} sesiones más`
      }}
    </button>
    <div v-if="otrasDesplegadas && grupos.otras.length" ref="otrasRoot">
      <p class="grp">Otras</p>
      <NotchFila
        v-for="s in grupos.otras"
        :key="s.pane_id"
        v-bind="filaGrupo(s, false)"
        @abrir="emit('abrir-sesion', $event)"
        @activar="activar"
        @opcion="(i) => elegirOpcion(s, i)"
        @texto="(t) => mandarTexto(s, t)"
        @permiso="(a) => resolverPermiso(s, a)"
        @pedido="(a, id) => resolverPedido(s, a, id)"
      />
    </div>
    <NotchNotas />
    <div class="foot">
      <span>Tocá una sesión para abrirla en Colmena</span>
      <span class="foot-btns">
        <button v-if="reunionDisponible" type="button" class="reunion-btn" @click="emit('abrir-reunion')">Reunión</button>
        <button type="button" class="open-btn" @click="emit('abrir-colmena')">Abrir Colmena</button>
      </span>
    </div>
  </div>
</template>

<style scoped>
.panel {
  display: grid;
  gap: 6px;
}
.grp {
  font-family: var(--font-mono);
  font-size: 0.66rem;
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-3);
  padding: 6px 6px 0;
  margin: 0;
}
.mas {
  justify-self: start;
  margin: 0;
  padding: 4px 8px;
  font: inherit;
  font-size: 0.74rem;
  color: var(--text-3);
  background: none;
  border: 0;
  border-radius: var(--r-pill);
  text-align: left;
  cursor: pointer;
}
.mas:hover {
  color: var(--text-2);
}
.mas:focus-visible {
  outline: 1px solid color-mix(in srgb, var(--accent) 50%, transparent);
  outline-offset: -1px;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 18%, transparent);
}
.foot {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  border-top: 1px solid var(--line);
  margin-top: 4px;
  padding: 9px 6px 0;
}
.foot span {
  font-size: 0.74rem;
  color: var(--text-3);
}
.foot-btns {
  display: flex;
  align-items: center;
  gap: 8px;
}
.reunion-btn {
  position: relative;
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text);
  background: color-mix(in srgb, var(--text) 9%, transparent);
  border: 0;
  border-radius: var(--r-pill);
  padding: 6px 14px;
  cursor: pointer;
  white-space: nowrap;
  touch-action: manipulation;
  transition: scale 150ms ease-out;
}
.reunion-btn:active {
  scale: 0.96;
}
.reunion-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.open-btn {
  font: inherit;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent);
  border: 0;
  border-radius: var(--r-pill);
  padding: 6px 14px;
  cursor: pointer;
  white-space: nowrap;
}
.open-btn:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
</style>
