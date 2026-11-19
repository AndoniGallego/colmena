<script setup lang="ts">
import { computed, nextTick, reactive, ref, watch } from 'vue'
import type { Nota } from '../../api/types'
import { contarPendientes, corto, notasNotch, TOPE_NOTAS_NOTCH } from '../../lib/notas'
import { useCompletarNotas } from '../../lib/useCompletarNotas'
import { soft } from '../../motion'
import { notas, marcarHecha } from '../../state/notas'
import { abrirColmena, abrirNotas } from '../../state/notch'

withDefaults(defineProps<{ cabecera?: boolean; anotar?: boolean }>(), { cabecera: true, anotar: true })

const todas = computed(() => notasNotch(notas.value))
const paraHacer = computed(() => contarPendientes(notas.value))
const { visibles, error, esHecha, completar, deshacer } = useCompletarNotas({
  base: () => todas.value,
  marcar: marcarHecha,
  tope: TOPE_NOTAS_NOTCH,
})

/** Ids que ya se vieron: solo late el marcador de una nota que aparece por primera vez. */
const vistas = new Set(notas.value.map((n) => n.id))
const recien = reactive(new Set<string>())
watch(notas, (l) => {
  for (const n of l) {
    if (vistas.has(n.id)) continue
    vistas.add(n.id)
    recien.add(n.id)
  }
})
const alEntrar = (el: Element) => recien.delete((el as HTMLElement).dataset.id ?? '')

const raiz = ref<HTMLElement>()
/** Texto para lectores de pantalla: el cambio a hecha no se ve en el nombre de ningún botón. */
const anuncio = ref('')

function enfocar(id: string, clase: 'accion' | 'deshacer') {
  const li = [...(raiz.value?.querySelectorAll<HTMLElement>('li.nota') ?? [])].find((el) => el.dataset.id === id)
  li?.querySelector<HTMLElement>(`button.${clase}`)?.focus()
}

/** El ✓ se reemplaza por Deshacer (y al revés): el foco sigue al botón nuevo para no caer al body. */
async function onCompletar(n: Nota) {
  anuncio.value = ''
  const pedido = completar(n)
  await nextTick()
  enfocar(n.id, 'deshacer')
  await pedido
  await nextTick()
  if (esHecha(n.id)) anuncio.value = 'Nota hecha'
  else enfocar(n.id, 'accion')
}

async function onDeshacer(id: string) {
  anuncio.value = ''
  await deshacer(id)
  await nextTick()
  if (esHecha(id)) return
  anuncio.value = 'Nota restaurada'
  enfocar(id, 'accion')
}

const nombre = (n: Nota) => `${corto(n.texto)}. Abre Colmena`

/** Con movimiento completo: entrada 200 ms con el latido del marcador de la nota recién guardada (320 ms) y salida 200 ms. Suave: fundido de 150 ms. */
const transicion = computed(() =>
  soft.value ? { name: 'fila-suave', duration: 150 } : { name: 'fila', duration: { enter: 320, leave: 200 } },
)

/** El colapso de alto necesita partir de un alto fijo. */
function fijarAlto(el: Element) {
  const li = el as HTMLElement
  li.style.height = `${li.offsetHeight}px`
}
</script>

<template>
  <section ref="raiz" class="notas" aria-label="Notas">
    <div v-if="cabecera" class="notas-cab">
      <h3>Notas<b v-if="paraHacer"> · {{ paraHacer }} para hacer</b></h3>
      <button v-if="anotar" type="button" class="anotar" @click="abrirNotas()">
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" aria-hidden="true">
          <path d="M8 3v10M3 8h10" />
        </svg>
        Anotar
      </button>
    </div>
    <slot />
    <TransitionGroup
      tag="ul"
      class="lista"
      :name="transicion.name"
      :duration="transicion.duration"
      @before-leave="fijarAlto"
      @after-enter="alEntrar"
    >
      <li
        v-for="n in visibles"
        :key="n.id"
        class="nota"
        :class="{ apunte: n.tipo === 'apunte', hecha: esHecha(n.id), recien: recien.has(n.id) }"
        :data-id="n.id"
      >
        <svg class="hex" viewBox="0 0 14 16" aria-hidden="true"><path d="M7 1.2 12.6 4.4v7.2L7 14.8 1.4 11.6V4.4Z" /></svg>
        <button type="button" class="txt" :aria-label="nombre(n)" @click="abrirColmena()">{{ n.texto }}</button>
        <button v-if="esHecha(n.id)" type="button" class="deshacer" @click="onDeshacer(n.id)">Deshacer</button>
        <button
          v-else-if="n.tipo === 'recordatorio'"
          type="button"
          class="accion"
          aria-label="Marcar hecha"
          @click="onCompletar(n)"
        >
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="m3.5 8.5 3 3 6-7" />
          </svg>
        </button>
        <span v-else aria-hidden="true" />
      </li>
    </TransitionGroup>
    <p v-if="!visibles.length" class="vacio">Sin notas. Anotá lo que no te querés olvidar.</p>
    <p class="sr-only" aria-live="polite">{{ anuncio }}</p>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <button v-if="todas.length > TOPE_NOTAS_NOTCH" type="button" class="ver-todas" @click="abrirColmena()">
      Ver las {{ todas.length }} notas
    </button>
  </section>
</template>

<style scoped>
.notas {
  display: grid;
}
.notas-cab {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 8px 6px;
}
.notas-cab h3 {
  margin: 0;
  font: 600 var(--t-xs) var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-3);
}
.notas-cab h3 b {
  text-transform: none;
  font-weight: 500;
  letter-spacing: 0;
  color: var(--text-4);
  font-variant-numeric: tabular-nums;
}
button {
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
}
.anotar {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-2);
  font: 500 var(--t-sm) var(--font-ui);
  cursor: pointer;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out,
    scale 150ms ease-out;
}
.anotar::before {
  content: '';
  position: absolute;
  inset: -6px -4px;
}
.anotar svg {
  width: 14px;
  height: 14px;
}
.lista {
  list-style: none;
  margin: 0;
  padding: 0;
}
.nota {
  display: grid;
  grid-template-columns: 18px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 44px;
  padding: 0 4px 0 8px;
  border-radius: var(--r-md);
  transition: background-color 120ms ease-out;
}
.hex {
  display: block;
  width: 14px;
  height: 16px;
}
.hex path {
  fill: none;
  stroke: var(--text-3);
  stroke-width: 1.5;
  transition:
    fill 220ms var(--ease-out),
    stroke 220ms var(--ease-out);
}
.nota.apunte .hex path {
  fill: var(--accent);
  stroke: var(--accent);
}
.nota.hecha .hex path {
  fill: var(--miel);
  stroke: var(--miel);
}
.txt {
  min-width: 0;
  height: 44px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--text);
  font: 400 var(--t-lg) var(--font-ui);
  text-align: left;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  cursor: pointer;
  text-decoration-line: line-through;
  text-decoration-color: transparent;
  transition:
    color 220ms ease-out,
    text-decoration-color 220ms ease-out;
}
.nota.hecha .txt {
  color: var(--text-3);
  text-decoration-color: color-mix(in srgb, var(--miel) 60%, transparent);
}
.accion {
  position: relative;
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out,
    scale 150ms ease-out;
}
.accion::before {
  content: '';
  position: absolute;
  inset: -6px;
}
.accion svg {
  width: 16px;
  height: 16px;
}
.deshacer {
  position: relative;
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--r-sm);
  background: var(--miel-soft);
  color: var(--miel);
  font: 600 var(--t-sm) var(--font-ui);
  cursor: pointer;
  transition: scale 150ms ease-out;
}
.deshacer::before {
  content: '';
  position: absolute;
  inset: -8px -4px;
}
.anotar:active,
.accion:active,
.deshacer:active {
  scale: var(--press-scale);
}
.anotar:focus-visible,
.accion:focus-visible,
.deshacer:focus-visible,
.txt:focus-visible,
.ver-todas:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  border-radius: var(--r-sm);
}
.vacio {
  margin: 0;
  padding: 8px 8px 4px;
  font-size: var(--t-sm);
  color: var(--text-3);
}
.error {
  margin: 0;
  padding: 4px 8px;
  font: 500 var(--t-sub-size)/1.3 var(--font-ui);
  color: var(--danger);
}
.ver-todas {
  justify-self: start;
  min-height: 44px;
  padding: 0 8px;
  border: 0;
  background: transparent;
  font: 400 var(--t-sm) var(--font-ui);
  color: var(--text-3);
  cursor: pointer;
  transition: color 120ms ease-out;
}
/* Movimiento: corto y discreto. Solo opacity y transform, más el colapso de alto al salir. */
.fila-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}
.fila-enter-active {
  transition:
    opacity 200ms var(--ease-out),
    transform 200ms var(--ease-out);
}
.fila-enter-active.recien .hex {
  animation: latido 320ms var(--ease-out);
}
@keyframes latido {
  50% {
    transform: scale(1.18);
  }
}
.fila-leave-active {
  overflow: hidden;
  transition:
    opacity 200ms ease-out,
    height 200ms var(--ease-out);
}
.fila-leave-to {
  opacity: 0;
  min-height: 0;
  height: 0 !important;
}
.fila-move {
  transition: transform 200ms var(--ease-out);
}
.fila-suave-enter-active,
.fila-suave-leave-active {
  transition: opacity 150ms ease-out;
}
.fila-suave-enter-from,
.fila-suave-leave-to {
  opacity: 0;
}
@media (prefers-reduced-motion: reduce) {
  .fila-enter-active,
  .fila-leave-active,
  .fila-move {
    transition: opacity 150ms ease-out;
  }
  .fila-enter-from {
    transform: none;
  }
  .fila-leave-to {
    min-height: 44px;
    height: auto !important;
  }
  .fila-enter-active.recien .hex {
    animation: none;
  }
}
@media (hover: hover) and (pointer: fine) {
  .anotar:hover {
    background: var(--surface-hover);
    color: var(--text);
  }
  .nota:hover {
    background: var(--surface);
  }
  .accion:hover {
    background: var(--surface-hover);
    color: var(--miel);
  }
  .ver-todas:hover {
    color: var(--text-2);
  }
}
</style>
