<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, shallowRef, watch } from 'vue'
import { ApiError, type Nota, type TipoNota } from '../api/types'
import { contarPendientes, filtrarNotas, type FiltroNotas } from '../lib/notas'
import { bajarTarjeta, cascadaEntrada, completarNota, levantarTarjeta, despedir, entrarNota, rebotarContador, reacomodar } from '../lib/notasMovimiento'
import { fechaLarga } from '../lib/time'
import { focusableIn, useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { desktop } from '../lib/viewport'
import { gsap, isSoft, useGsap } from '../motion'
import { boardState } from '../state/app'
import { borrarNota, crearNota, editarNota, marcarHecha, notas, saltoMensaje } from '../state/notas'
import { openSessionChat } from '../state/session'
import Icon from './Icon.vue'
import NotaTarjeta from './NotaTarjeta.vue'
import SegControl from './SegControl.vue'
import ViewFrame from './ViewFrame.vue'

const props = defineProps<{ visible: boolean }>()
const { run } = useGsap()

const FILTROS: { value: FiltroNotas; label: string }[] = [
  { value: 'todas', label: 'Todas' },
  { value: 'para-hacer', label: 'Para hacer' },
  { value: 'apuntes', label: 'Apuntes' },
  { value: 'hechas', label: 'Hechas' },
]
const VACIO: Record<FiltroNotas, string> = {
  todas: 'Todavía no hay notas. Anotá la primera arriba.',
  'para-hacer': 'Nada para hacer. Disfrutalo.',
  apuntes: 'No hay apuntes sueltos.',
  hechas: 'Todavía no completaste ningún recordatorio.',
}

const filtro = ref<FiltroNotas>('todas')
const filtradas = computed(() => filtrarNotas(notas.value, filtro.value))
const mostradas = shallowRef<Nota[]>(filtradas.value)
const pendientesN = computed(() => contarPendientes(notas.value))
const hechasN = computed(() => notas.value.filter((n) => n.tipo === 'recordatorio' && !!n.hecha_at).length)
const subtitulo = computed(() => (pendientesN.value ? `${pendientesN.value} para hacer` : 'Nada pendiente'))

const vivas = computed(() => {
  const s = new Set<string>()
  for (const ws of boardState.value.board?.workspaces ?? [])
    for (const tab of ws.tabs) for (const a of tab.agents) if (a.session_id) s.add(a.session_id)
  return s
})
const viva = (n: Nota) => !!n.origen && vivas.value.has(n.origen.sid)

const error = ref('')
// Los errores de lo que se hace desde el detalle se muestran ahí, no detrás de la hoja.
const errorDetalle = ref('')
function mensaje(e: unknown, base: string) {
  if (e instanceof ApiError && (e.status === 503 || e.status === 422) && e.detail) return `${base} ${e.detail}`
  return `${base} Probá de nuevo.`
}

// ---------- tablero: la lista visible se sincroniza con animación ----------
const grid = ref<HTMLElement | null>(null)
const frasco = ref<HTMLElement | null>(null)
const vistos = new Set(notas.value.map((n) => n.id))
// Si la vista se monta antes de que lleguen las notas, la primera carga no hace la entrada.
let sembrado = notas.value.length > 0
let ocupada = 0
let cola: Promise<void> = Promise.resolve()

const tarjeta = (id: string) => [...(grid.value?.children ?? [])].find((c) => (c as HTMLElement).dataset.id === id)

function cascada() {
  const el = grid.value
  if (!el) return
  cascadaEntrada([...el.children])
  rebotarContador(frasco.value?.querySelector('.frasco-hex') ?? null)
}

async function sincronizar() {
  const l = filtradas.value
  let primera = false
  if (!sembrado && notas.value.length) {
    sembrado = true
    primera = true
    notas.value.forEach((n) => vistos.add(n.id))
  }
  const nuevas = l.filter((n) => !vistos.has(n.id)).map((n) => n.id)
  l.forEach((n) => vistos.add(n.id))
  const el = grid.value
  if (!el || !props.visible) {
    mostradas.value = l
    return
  }
  if (primera) {
    mostradas.value = l
    await nextTick()
    cascada()
    return
  }
  const ids = new Set(l.map((n) => n.id))
  const celu = !desktop.value
  await despedir([...el.children].filter((c) => !ids.has((c as HTMLElement).dataset.id ?? '')), celu)
  await reacomodar(
    el,
    () => {
      mostradas.value = l
    },
    celu,
  )
  for (const id of nuevas) {
    const c = tarjeta(id)
    if (c) entrarNota(c)
  }
}
function aplicar(): Promise<void> {
  cola = cola.then(sincronizar, sincronizar)
  return cola
}
watch(filtradas, () => {
  if (!ocupada) void aplicar()
})
// El frasco suma recién cuando la nota aterriza.
const hechasFrasco = ref(hechasN.value)
watch(hechasN, (v) => {
  if (!ocupada) hechasFrasco.value = v
})

// ---------- anotar ----------
const texto = ref('')
const tipoNuevo = ref<TipoNota>('apunte')
const guardando = ref(false)

async function guardar(e?: KeyboardEvent) {
  if (e?.isComposing) return
  const t = texto.value.trim()
  if (!t || guardando.value) return
  if (t.length > 4000) {
    error.value = 'Es muy larga: hasta 4000 letras.'
    return
  }
  guardando.value = true
  error.value = ''
  if (filtro.value !== 'todas' && !(filtro.value === 'apuntes' && tipoNuevo.value === 'apunte') && !(filtro.value === 'para-hacer' && tipoNuevo.value === 'recordatorio'))
    filtro.value = 'todas'
  try {
    await crearNota({ tipo: tipoNuevo.value, texto: t })
    texto.value = ''
  } catch (err) {
    error.value = mensaje(err, 'No pude guardar la nota.')
  } finally {
    guardando.value = false
  }
}

// ---------- completar ----------
const completando = new Set<string>()
async function completar(n: Nota, hecha: boolean, enDetalle = false) {
  if (completando.has(n.id)) return
  const err = enDetalle ? errorDetalle : error
  err.value = ''
  if (!hecha) {
    try {
      await marcarHecha(n.id, false)
    } catch (e) {
      err.value = mensaje(e, 'No pude volverla a pendiente.')
    }
    return
  }
  completando.add(n.id)
  ocupada++
  const el = tarjeta(n.id)
  const anim = el && frasco.value ? completarNota(el, frasco.value) : Promise.resolve()
  const [, r] = await Promise.allSettled([anim, marcarHecha(n.id, true)])
  ocupada--
  completando.delete(n.id)
  hechasFrasco.value = hechasN.value
  if (r.status === 'rejected') err.value = mensaje(r.reason, 'No pude marcarla como hecha.')
  await aplicar()
  // Vuelve sellada si sigue a la vista (o restaurada si falló).
  const c = tarjeta(n.id)
  if (c) entrarNota(c)
}

// ---------- detalle ----------
const seleccionId = ref<string | null>(null)
const seleccion = computed(() => notas.value.find((n) => n.id === seleccionId.value) ?? null)
const editando = ref(false)
const borrador = ref('')
const borradorTipo = ref<TipoNota>('apunte')
const confirmarBorrar = ref(false)
const ocupadoDetalle = ref(false)
const detalle = ref<HTMLElement | null>(null)
const TIPOS: { value: TipoNota; label: string }[] = [
  { value: 'recordatorio', label: 'Para hacer' },
  { value: 'apunte', label: 'Apunte' },
]

let levantando = false
async function seleccionar(n: Nota) {
  if (!desktop.value && !isSoft()) {
    const c = tarjeta(n.id)
    if (c) {
      if (levantando) return
      levantando = true
      try {
        await levantarTarjeta(c)
      } finally {
        levantando = false
      }
      seleccionId.value = seleccionId.value === n.id ? null : n.id
      bajarTarjeta(c)
      return
    }
  }
  seleccionId.value = seleccionId.value === n.id && !desktop.value ? null : n.id
  const c = tarjeta(n.id)
  if (c && !isSoft()) run(() => gsap.fromTo(c, { scale: 0.92 }, { scale: 1, duration: 0.5, ease: 'back.out(3)', clearProps: 'transform' }))
}
function cerrarDetalle() {
  seleccionId.value = null
}
watch(seleccionId, async () => {
  editando.value = false
  confirmarBorrar.value = false
  errorDetalle.value = ''
  if (!desktop.value || !seleccionId.value) return
  await nextTick()
  const kids = detalle.value?.querySelectorAll('.dt-anim')
  if (kids?.length && !isSoft()) run(() => gsap.fromTo(kids, { opacity: 0, y: 8 }, { opacity: 1, y: 0, stagger: 0.05, duration: 0.3, clearProps: 'transform,opacity' }))
})
watch(seleccion, (s) => {
  if (!s && seleccionId.value) seleccionId.value = null
})
watch(
  () => props.visible,
  (v) => {
    if (!v && !desktop.value) seleccionId.value = null
  },
)

function empezarEdicion() {
  const s = seleccion.value
  if (!s) return
  borrador.value = s.texto
  borradorTipo.value = s.tipo
  editando.value = true
}
async function guardarEdicion() {
  const s = seleccion.value
  const t = borrador.value.trim()
  if (!s || !t || ocupadoDetalle.value) return
  const cambios: { texto?: string; tipo?: TipoNota } = {}
  if (t !== s.texto) cambios.texto = t
  if (borradorTipo.value !== s.tipo) cambios.tipo = borradorTipo.value
  if (!cambios.texto && !cambios.tipo) {
    editando.value = false
    return
  }
  ocupadoDetalle.value = true
  errorDetalle.value = ''
  try {
    await editarNota(s.id, cambios)
    editando.value = false
  } catch (err) {
    errorDetalle.value = mensaje(err, 'No pude guardar el cambio.')
  } finally {
    ocupadoDetalle.value = false
  }
}
function teclaEdicion(e: KeyboardEvent) {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
    e.preventDefault()
    void guardarEdicion()
  } else if (e.key === 'Escape') {
    e.stopPropagation()
    editando.value = false
  }
}
async function borrar() {
  const s = seleccion.value
  if (!s || ocupadoDetalle.value) return
  if (!confirmarBorrar.value) {
    confirmarBorrar.value = true
    return
  }
  ocupadoDetalle.value = true
  errorDetalle.value = ''
  try {
    await borrarNota(s.id)
    seleccionId.value = null
  } catch (err) {
    errorDetalle.value = mensaje(err, 'No pude borrar la nota.')
  } finally {
    ocupadoDetalle.value = false
    confirmarBorrar.value = false
  }
}
function irASesion(n: Nota) {
  if (!n.origen || !viva(n)) return
  saltoMensaje.value = { sid: n.origen.sid, ts: n.origen.ts }
  cerrarDetalle()
  openSessionChat(n.origen.sid)
}

function onKey(e: KeyboardEvent) {
  if (e.key === 'Escape' && seleccionId.value && props.visible && !editando.value) cerrarDetalle()
}
onMounted(() => {
  document.addEventListener('keydown', onKey)
  if (mostradas.value.length) void nextTick(cascada)
})
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKey)
  // Si se va a mitad de un completar, no quedan tweens vivos ni el clon volando sobre la app.
  document.querySelectorAll('.nota-vuelo').forEach((c) => c.remove())
  if (grid.value) gsap.killTweensOf([grid.value, ...grid.value.querySelectorAll('*')])
  if (frasco.value) gsap.killTweensOf(frasco.value)
})

// En el celu el detalle es un diálogo: toma el foco, lo encierra y al cerrar vuelve a la tarjeta.
const hojaAbierta = () => !desktop.value && !!seleccion.value
const { onKeydown: teclaHoja } = useFocusTrap(detalle, hojaAbierta, {
  onEscape: () => {
    if (editando.value) editando.value = false
    else cerrarDetalle()
  },
  initial: () => (detalle.value ? (focusableIn(detalle.value).find((b) => b.matches('.acts button')) ?? null) : null),
})
useSheetSwipe(detalle, cerrarDetalle, { activo: () => !desktop.value })

// Hoja del detalle en el celu.
function hojaEntra(el: Element, done: () => void) {
  const panel = el.querySelector('.sheet-panel')
  const scrim = el.querySelector('.sheet-scrim')
  if (isSoft() || !panel) {
    gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.15, onComplete: done, clearProps: 'opacity' })
    return
  }
  gsap.fromTo(scrim, { opacity: 0 }, { opacity: 1, duration: 0.3 })
  gsap.fromTo(panel, { yPercent: 100 }, { yPercent: 0, duration: 0.45, ease: 'orq.sheet', onComplete: done, clearProps: 'transform' })
}
function hojaSale(el: Element, done: () => void) {
  const panel = el.querySelector('.sheet-panel')
  if (isSoft() || !panel) {
    gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done })
    return
  }
  gsap.to(el.querySelector('.sheet-scrim'), { opacity: 0, duration: 0.25 })
  gsap.to(panel, { yPercent: 100, duration: 0.28, ease: 'power2.in', onComplete: done })
}
</script>

<template>
  <ViewFrame class="notas" aria-label="Notas" title="Notas" :subtitle="subtitulo" body-scroll>
    <template #actions>
      <button
        ref="frasco"
        type="button"
        class="frasco hit"
        :aria-label="`${hechasFrasco} hechas: ver las hechas`"
        @click="filtro = 'hechas'"
      >
        <span class="frasco-hex mono">{{ hechasFrasco }}</span>
        <span class="frasco-l">Hechas</span>
      </button>
    </template>
    <template #toolbar>
      <SegControl v-model="filtro" class="notas-filtros" :options="FILTROS" label="Filtrar notas" />
    </template>

    <div class="notas-cuerpo" :class="{ desk: desktop }">
      <div class="notas-tablero">
        <div class="notas-anotar" :class="`t-${tipoNuevo}`">
          <button
            type="button"
            class="anotar-tipo hit"
            :aria-label="tipoNuevo === 'apunte' ? 'Tipo: apunte. Tocá para que sea para hacer' : 'Tipo: para hacer. Tocá para que sea apunte'"
            @click="tipoNuevo = tipoNuevo === 'apunte' ? 'recordatorio' : 'apunte'"
          >
            <i class="anotar-sello" aria-hidden="true" />
            <span>{{ tipoNuevo === 'apunte' ? 'Apunte' : 'Para hacer' }}</span>
          </button>
          <input
            v-model="texto"
            class="notas-campo"
            type="text"
            maxlength="4000"
            enterkeyhint="done"
            autocomplete="off"
            aria-label="Nueva nota"
            :placeholder="tipoNuevo === 'apunte' ? (desktop ? 'Anotá algo y apretá Enter' : 'Anotá algo…') : '¿Qué tenés que hacer?'"
            @keydown.enter.prevent="guardar($event)"
          />
          <button type="button" class="btn btn-primary btn-sm anotar-ok" :disabled="!texto.trim() || guardando" @click="guardar()">Guardar</button>
        </div>
        <p v-if="error" class="notas-error" role="alert">{{ error }}</p>

        <div v-show="mostradas.length" ref="grid" class="notas-grid">
          <NotaTarjeta
            v-for="n in mostradas"
            :key="n.id"
            :nota="n"
            :seleccionada="n.id === seleccionId"
            :sesion-viva="viva(n)"
            :deslizable="!desktop && n.tipo === 'recordatorio' && !n.hecha_at"
            @seleccionar="seleccionar(n)"
            @completar="(h: boolean) => completar(n, h)"
            @abrir="irASesion(n)"
          />
        </div>
        <div v-if="!mostradas.length" class="notas-vacio">
          <i class="vacio-celda" aria-hidden="true" />
          <p>{{ VACIO[filtro] }}</p>
        </div>
      </div>

      <Teleport to="body" :disabled="desktop">
        <Transition :css="false" @enter="hojaEntra" @leave="hojaSale">
          <div v-if="desktop || seleccion" class="detalle-raiz" :class="desktop ? 'en-columna' : 'sheet-root'" @keydown="!desktop && teclaHoja($event)">
            <div v-if="!desktop" class="sheet-scrim" @click="cerrarDetalle" />
            <section
              ref="detalle"
              class="detalle"
              :class="{ 'sheet-panel': !desktop }"
              :role="desktop ? undefined : 'dialog'"
              :aria-label="desktop ? 'Detalle de la nota' : undefined"
              :aria-modal="desktop ? undefined : 'true'"
              aria-live="polite"
            >
              <template v-if="seleccion">
                <span v-if="!desktop" class="sheet-grip" aria-hidden="true" />
                <span class="dk dt-anim">
                  <i class="dk-sello" :class="seleccion.tipo === 'apunte' ? 'apunte' : seleccion.hecha_at ? 'hecha' : 'todo'" aria-hidden="true" />
                  {{ seleccion.tipo === 'apunte' ? 'Apunte' : seleccion.hecha_at ? 'Hecha' : 'Para hacer' }}
                </span>
                <template v-if="editando">
                  <SegControl v-model="borradorTipo" class="dt-tipo" :options="TIPOS" label="Tipo de nota" />
                  <textarea
                    v-model="borrador"
                    class="dt-edit"
                    rows="5"
                    maxlength="4000"
                    aria-label="Texto de la nota"
                    @keydown="teclaEdicion"
                  />
                  <div class="acts">
                    <button type="button" class="btn btn-primary btn-sm" :disabled="!borrador.trim() || ocupadoDetalle" @click="guardarEdicion">Guardar</button>
                    <button type="button" class="btn btn-ghost btn-sm" @click="editando = false">Cancelar</button>
                  </div>
                </template>
                <template v-else>
                  <p class="dt dt-anim">{{ seleccion.texto }}</p>
                  <span class="dm dt-anim">
                    <template v-if="seleccion.origen">de <b>{{ seleccion.origen.nombre || 'una sesión' }}</b></template>
                    <template v-else>idea suelta</template>
                    · {{ fechaLarga(seleccion.creada_at, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) }}
                  </span>
                  <span v-if="seleccion.origen && !viva(seleccion)" class="dm-ida dt-anim">la sesión ya no está</span>
                  <div class="acts dt-anim">
                    <button v-if="seleccion.origen" type="button" class="btn btn-ghost btn-sm hit" :disabled="!viva(seleccion)" @click="irASesion(seleccion)">
                      <Icon name="arrow-right" :size="14" /> Ir a la sesión
                    </button>
                    <button v-if="seleccion.tipo === 'recordatorio'" type="button" class="btn btn-ghost btn-sm hit dt-miel" @click="completar(seleccion, !seleccion.hecha_at, true)">
                      <Icon name="check" :size="14" /> {{ seleccion.hecha_at ? 'Volver a pendiente' : 'Marcar hecha' }}
                    </button>
                    <button type="button" class="btn btn-ghost btn-sm hit" @click="empezarEdicion"><Icon name="pen" :size="14" /> Editar</button>
                    <button
                      type="button"
                      class="btn btn-sm hit"
                      :class="confirmarBorrar ? 'btn-danger' : 'btn-ghost'"
                      :disabled="ocupadoDetalle"
                      @click="borrar"
                      @blur="confirmarBorrar = false"
                    >
                      <Icon name="trash" :size="14" /> {{ confirmarBorrar ? '¿Seguro? Borrar' : 'Borrar' }}
                    </button>
                  </div>
                </template>
                <p v-if="errorDetalle" class="notas-error dt-error" role="alert">{{ errorDetalle }}</p>
              </template>
              <p v-else class="detalle-vacio">Tocá una nota para verla entera.</p>
            </section>
          </div>
        </Transition>
      </Teleport>
    </div>
  </ViewFrame>
</template>

<style scoped>
.notas-cuerpo {
  padding-bottom: 12px;
}
.notas-cuerpo.desk {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 340px);
  gap: 22px;
  align-items: start;
}
.notas-tablero {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* Frasco de Hechas: destino del vuelo al completar. */
.frasco {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 2px 4px;
  border-radius: var(--r-sm);
  touch-action: manipulation;
}
.frasco-hex {
  display: grid;
  place-items: center;
  width: 30px;
  height: 34px;
  background: var(--miel);
  color: var(--bg);
  font-size: var(--t-md);
  font-weight: 700;
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
}
.frasco-l {
  font: 600 var(--t-2xs) / 1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-3);
}
.frasco:focus-visible {
  outline: 2px solid var(--miel);
  outline-offset: 2px;
}

.notas-filtros {
  width: min(100%, 460px);
}
/* La pastilla de la pestaña activa se desliza a la tocada. */
.notas-filtros :deep(.seg-knob) {
  transition: translate 0.28s var(--ease-out);
}
:root[data-motion='soft'] .notas-filtros :deep(.seg-knob) {
  transition: translate 0.15s linear;
}
.notas-filtros :deep(.seg-btn) {
  padding: 0 6px;
  white-space: nowrap;
}

/* Campo para anotar. */
.notas-anotar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 6px 6px 8px;
  border-radius: var(--r-lg);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.notas-anotar:focus-within {
  box-shadow: inset 0 0 0 1.5px var(--accent-line);
}
.anotar-tipo {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 7px;
  min-height: 32px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  font: 600 var(--t-2xs) / 1 var(--font-mono);
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-2);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line);
  touch-action: manipulation;
}
.anotar-sello {
  width: 12px;
  height: 14px;
  background: var(--accent);
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  position: relative;
  transition: transform 0.4s var(--spring);
}
.t-recordatorio .anotar-sello {
  background: var(--text-3);
  transform: rotate(60deg);
}
.t-recordatorio .anotar-sello::after {
  content: '';
  position: absolute;
  inset: 2px;
  clip-path: inherit;
  background: var(--surface-2);
}
.notas-campo {
  flex: 1;
  min-width: 0;
  min-height: 36px;
  border: 0;
  background: transparent;
  color: var(--text);
  font: 500 var(--t-lg) var(--font-ui);
  outline: none;
}
.notas-campo::placeholder {
  color: var(--text-4);
}
.anotar-ok {
  flex: none;
}
.notas-error {
  margin: 0;
  font-size: var(--t-sm);
  color: var(--danger);
}

/* Tarjetas. */
.notas-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 150px), 1fr));
  grid-auto-rows: minmax(140px, auto);
  gap: 10px;
}
/* En el celu la tarjeta se ajusta al contenido: sin alto mínimo ni hueco forzado. */
.notas-cuerpo:not(.desk) .notas-grid {
  grid-auto-rows: auto;
}
/* En escritorio las tarjetas llenan el ancho y muestran más texto. */
.notas-cuerpo.desk .notas-grid {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  grid-auto-rows: minmax(160px, auto);
  gap: 12px;
}
.notas-cuerpo.desk .notas-grid :deep(.nota-texto) {
  -webkit-line-clamp: 6;
  line-clamp: 6;
}
.dt-error {
  margin-top: 4px;
}
.notas-vacio {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px 12px;
  color: var(--text-3);
  text-align: center;
}
.notas-vacio p {
  margin: 0;
  max-width: 34ch;
}
.vacio-celda {
  width: 56px;
  height: 64px;
  background: var(--line-2);
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
  position: relative;
}
.vacio-celda::after {
  content: '';
  position: absolute;
  inset: 1.5px;
  clip-path: inherit;
  background: var(--bg);
}

/* Detalle: columna en escritorio, hoja en el celu. */
.detalle-raiz.en-columna {
  position: sticky;
  top: 0;
}
.detalle {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.en-columna .detalle {
  min-height: 140px;
  padding: 16px;
  border-radius: var(--r-card);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
.sheet-root .detalle {
  padding-left: max(18px, env(safe-area-inset-left));
  padding-right: max(18px, env(safe-area-inset-right));
}
.dk {
  display: flex;
  align-items: center;
  gap: 8px;
  font: 600 var(--t-2xs) / 1 var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-3);
}
.dk-sello {
  width: 14px;
  height: 16px;
  position: relative;
  clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
}
.dk-sello.apunte {
  background: var(--accent);
}
.dk-sello.hecha {
  background: var(--miel);
}
.dk-sello.todo {
  background: var(--text-3);
}
.dk-sello.todo::after {
  content: '';
  position: absolute;
  inset: 2px;
  clip-path: inherit;
  background: var(--surface);
}
.dt {
  margin: 0;
  font: 600 20px / 1.3 var(--font-display);
  letter-spacing: -0.01em;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 46dvh;
  overflow-y: auto;
}
.dm {
  font: 500 var(--t-sm) var(--font-mono);
  color: var(--text-3);
}
.dm b {
  color: var(--accent);
  font-weight: 500;
}
.dm-ida {
  font-size: var(--t-sm);
  color: var(--text-4);
}
.acts {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 4px;
}
.dt-miel :deep(svg) {
  color: var(--miel);
}
.dt-edit {
  width: 100%;
  resize: vertical;
  min-height: 110px;
  padding: 10px 12px;
  border: 0;
  border-radius: var(--r-md);
  background: var(--bg-2);
  color: var(--text);
  box-shadow: inset 0 0 0 1px var(--line-2);
  font: 500 var(--t-lg) / 1.45 var(--font-ui);
  outline: none;
}
.dt-edit:focus-visible {
  box-shadow: inset 0 0 0 1.5px var(--accent-line);
}
.detalle-vacio {
  margin: auto 0;
  color: var(--text-3);
  font-size: var(--t-md);
}

@media (hover: hover) and (pointer: fine) {
  .anotar-tipo:hover {
    color: var(--text);
  }
  .frasco:hover .frasco-l {
    color: var(--miel);
  }
}
@media (pointer: coarse) {
  .anotar-ok,
  .acts .btn {
    min-height: 44px;
  }
}
@media (max-width: 899px) {
  .notas-campo,
  .dt-edit {
    font-size: 16px;
  }
}
:root[data-motion='soft'] .anotar-sello {
  transition: none;
}
</style>
