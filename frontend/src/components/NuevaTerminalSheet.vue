<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { useKeyboard } from '../lib/keyboard'
import { ApiError, type ConfianzaPreparar } from '../api/types'
import { getTerminalesCarpetas, postTerminalesNueva, postTerminalesNuevaTarea, postTerminalesNuevaTareaConfiar } from '../state/app'
import { useListoPanel } from '../lib/listoPanel'
import { capturandoAtajo, comboDe, etiquetaDe } from '../state/atajosEstado'
import ListoOverlay from './ListoOverlay.vue'
import {
  armarCuerpoNueva,
  armarCuerpoTarea,
  carpetaSugerida,
  esAtajoEnviar,
  filtrarCarpetas,
  guardarModo,
  guardarUltimoRepo,
  idOperacionNueva,
  leerModo,
  leerUltimoRepo,
  MAX_TAREA,
  MAX_NOTA_TICKET,
  placeholderNombre,
  repoInicial,
  soloRepos,
  validarNombreNueva,
  ramaDeTicket,
  validarRamaNueva,
  validarTarea,
  validarTicket,
  type CarpetaItem,
  type GrupoItem,
  type ModoNueva,
  type TipoNueva,
} from '../lib/nuevaTerminal'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'

const props = defineProps<{ open: boolean; grupoInicial?: string; tareaInicial?: string }>()
const emit = defineEmits<{ close: [] }>()
const atajoTexto = computed(() => etiquetaDe('crear-terminal').replace(' ', '+'))
const { run } = useGsap()
const kb = useKeyboard()
const panel = ref<HTMLElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => props.open, { onEscape: () => emit('close') })
useSheetSwipe(panel, () => emit('close'))
const layout = computed(() => (kb.open.value && kb.height.value ? { height: `${kb.height.value}px`, top: `${kb.top.value}px` } : undefined))

const carpetas = ref<CarpetaItem[]>([])
const grupos = ref<GrupoItem[]>([])
const grupoId = ref('')
const cargando = ref(false)
const error = ref('')
const busqueda = ref('')
const carpetaRuta = ref('')
const tipo = ref<TipoNueva>('shell')
const modo = ref<ModoNueva>('terminal')
const tarea = ref('')
const ticket = ref('')
const rama = ref('')
const masOpciones = ref(false)
const nombre = ref('')
const opId = ref('')
const abriendo = ref(false)
const pideConfianza = ref<ConfianzaPreparar | null>(null)
const avisoPuertos = ref(false)
const cierre = () => emit('close')
const { listo: listoPantalla, listoTxt, mostrarListo } = useListoPanel(cierre)

const carpetaSel = computed(() => carpetas.value.find((c) => c.ruta === carpetaRuta.value) ?? null)
const listado = computed(() => filtrarCarpetas(carpetas.value, busqueda.value))
const mostrarBuscador = computed(() => carpetas.value.length > 8)
const mostrarGrupos = computed(() => grupos.value.length > 0)
const errNombre = computed(() => validarNombreNueva(nombre.value))
const listoTerminal = computed(() => !!carpetaSel.value && !errNombre.value && !abriendo.value)
const repos = computed(() => soloRepos(carpetas.value))
const reposListado = computed(() => filtrarCarpetas(repos.value, busqueda.value))
const mostrarBuscadorRepos = computed(() => repos.value.length > 8)
const errTicket = computed(() => validarTicket(ticket.value))
const ramaTicket = computed(() => ramaDeTicket(ticket.value))
const errTarea = computed(() => (tarea.value ? validarTarea(tarea.value, ticket.value) : ''))
const errRama = computed(() => validarRamaNueva(rama.value))
const listoTarea = computed(() => !!carpetaSel.value && !errTicket.value && !validarTarea(tarea.value, ticket.value) && !errNombre.value && !errRama.value && !abriendo.value)
const listo = computed(() => (modo.value === 'tarea' ? listoTarea.value : listoTerminal.value))
const phNombre = computed(() => placeholderNombre(carpetaSel.value))

const msg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f)

watch(
  () => props.open,
  async (on) => {
    if (!on) return
    error.value = busqueda.value = nombre.value = tarea.value = rama.value = ticket.value = ''
    pideConfianza.value = null
    avisoPuertos.value = false
    masOpciones.value = false
    const conBrief = props.tareaInicial !== undefined
    modo.value = conBrief ? 'tarea' : props.grupoInicial ? 'terminal' : leerModo()
    if (conBrief) tarea.value = props.tareaInicial!.slice(0, MAX_TAREA)
    carpetaRuta.value = ''
    grupoId.value = ''
    tipo.value = 'shell'
    opId.value = idOperacionNueva()
    cargando.value = true
    try {
      const data = await getTerminalesCarpetas()
      carpetas.value = data.carpetas
      grupos.value = data.grupos ?? []
      if (props.grupoInicial && grupos.value.some((g) => g.id === props.grupoInicial)) grupoId.value = props.grupoInicial
      if (modo.value === 'tarea' && !conBrief) elegirRepoInicial()
    } catch (e) {
      error.value = msg(e, 'No pude leer las carpetas')
    } finally {
      cargando.value = false
    }
  },
)

function elegirRepoInicial() {
  if (carpetaSel.value && carpetaSel.value.repo) return
  carpetaRuta.value = repoInicial(repos.value, leerUltimoRepo(), null)?.ruta ?? ''
}

function cambiarModo(m: ModoNueva) {
  if (modo.value === m) return
  modo.value = m
  guardarModo(m)
  error.value = busqueda.value = ''
  if (m === 'tarea') elegirRepoInicial()
}

watch(grupoId, (id) => {
  if (!id) return
  const sug = carpetaSugerida(id, grupos.value, carpetas.value)
  if (sug) carpetaRuta.value = sug.ruta
})

function textoListoTarea(r: Awaited<ReturnType<typeof postTerminalesNuevaTarea>>) {
  if (r.pegado === false) return 'Tarea abierta: pegá el mensaje a mano'
  const p = r.preparar
  if (!p) return 'Tarea abierta'
  const n = p.copiados.length
  const partes = [
    n ? `${n} ${n === 1 ? 'archivo copiado' : 'archivos copiados'}` : '',
    p.puerto !== null ? `${p.puertos === 1 ? 'puerto' : 'puertos'} ${p.puerto}${p.puertos > 1 ? `–${p.puerto + p.puertos - 1}` : ''}` : '',
  ].filter(Boolean)
  return `Tarea abierta${partes.length ? `: ${partes.join(', ')}` : ''}`
}

async function enviarTarea() {
  if (!carpetaSel.value) return
  abriendo.value = true
  error.value = ''
  try {
    const r = await postTerminalesNuevaTarea(armarCuerpoTarea(carpetaSel.value, tarea.value, nombre.value, rama.value, opId.value, ticket.value, grupoId.value))
    guardarUltimoRepo(carpetaSel.value.ruta)
    if (r.preparar?.puertos_fijos) avisoPuertos.value = true
    mostrarListo(textoListoTarea(r))
  } catch (e) {
    if (e instanceof ApiError && e.codigo === 'requiere_confianza' && e.confianza) pideConfianza.value = e.confianza
    else error.value = msg(e, 'No pude abrir la tarea')
  } finally {
    abriendo.value = false
  }
}

async function abrirTarea() {
  if (!listoTarea.value || !carpetaSel.value) return
  haptic([8, 30, 8])
  await enviarTarea()
}

async function confiarYAbrir() {
  const c = pideConfianza.value
  if (!c || abriendo.value) return
  abriendo.value = true
  try {
    await postTerminalesNuevaTareaConfiar({ repo: c.repo, setup_sha256: c.setup_sha256, script_sha256: c.script_sha256 })
  } catch (e) {
    error.value = msg(e, 'No pude guardar la confianza')
    pideConfianza.value = null
    abriendo.value = false
    return
  }
  pideConfianza.value = null
  abriendo.value = false
  await enviarTarea()
}

function noConfiar() {
  pideConfianza.value = null
}

function onTareaKeydown(e: KeyboardEvent) {
  if (capturandoAtajo.value || !esAtajoEnviar(e, comboDe('crear-terminal'))) return
  e.preventDefault()
  void abrirTarea()
}

async function abrir() {
  if (modo.value === 'tarea') return abrirTarea()
  if (!listo.value || !carpetaSel.value) return
  haptic([8, 30, 8])
  abriendo.value = true
  error.value = ''
  try {
    await postTerminalesNueva(armarCuerpoNueva(carpetaSel.value, tipo.value, nombre.value, opId.value, grupoId.value || null))
    mostrarListo(tipo.value === 'claude' ? 'Claude abierto' : 'Terminal abierta')
  } catch (e) {
    error.value = msg(e, 'No pude abrirla')
  } finally {
    abriendo.value = false
  }
}

function onEnter(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(el.querySelector('.sheet-scrim'), { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0)
    tl.fromTo(el.querySelector('.cs-panel'), { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
  })
}
function onLeave(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.to(el.querySelector('.sheet-scrim'), { opacity: 0, duration: 0.22 }, 0)
    tl.to(el.querySelector('.cs-panel'), { yPercent: 100, duration: 0.3, ease: 'power3.in' }, 0)
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="onEnter" @leave="onLeave">
      <div v-if="open" class="sheet-root cs" :style="layout" @keydown="onKeydown">
        <div class="sheet-scrim cs-back" @click="emit('close')" />
        <form ref="panel" class="sheet-panel cs-panel" role="dialog" aria-modal="true" aria-labelledby="nt-title" @submit.prevent="abrir">
          <i class="sheet-grip grip" aria-hidden="true" />
          <div class="sheet-stagger cs-stagger">
            <h2 id="nt-title" class="sheet-title title"><Icon name="terminal" :size="18" /> {{ modo === 'tarea' ? 'Nueva tarea' : 'Nueva terminal' }}</h2>

            <span class="seg modo" role="group" aria-label="Qué querés abrir">
              <button type="button" :aria-pressed="modo === 'terminal'" @click="cambiarModo('terminal')">Terminal</button>
              <button type="button" :aria-pressed="modo === 'tarea'" @click="cambiarModo('tarea')">Nueva tarea</button>
            </span>

            <label v-if="mostrarGrupos" class="field">
              <span>Grupo</span>
              <select v-model="grupoId" class="sel">
                <option value="">Nuevo</option>
                <option v-for="g in grupos" :key="g.id" :value="g.id">{{ g.nombre }}</option>
              </select>
            </label>

            <template v-if="modo === 'tarea'">
              <label v-if="mostrarBuscadorRepos" class="field">
                <span>Buscar repo</span>
                <input v-model="busqueda" type="search" autocomplete="off" spellcheck="false" placeholder="Nombre o ruta" />
              </label>

              <div class="field">
                <span>Repo</span>
                <div v-if="cargando" class="st"><span class="spin" aria-hidden="true" /> Cargando…</div>
                <p v-else-if="!repos.length" class="st">No hay repos de git entre las carpetas permitidas.</p>
                <div v-else class="pick" role="listbox" aria-label="Repo">
                  <button
                    v-for="c in reposListado"
                    :key="c.ruta"
                    type="button"
                    class="carp"
                    :class="{ on: carpetaRuta === c.ruta }"
                    :aria-pressed="carpetaRuta === c.ruta"
                    @click="carpetaRuta = c.ruta"
                  >
                    <span class="nom">{{ c.nombre }}</span>
                    <span class="ruta mono">{{ c.ruta }}</span>
                  </button>
                </div>
              </div>

              <label class="field">
                <span>Ticket <i>(opcional)</i></span>
                <input
                  :value="ticket"
                  class="ticket"
                  maxlength="20"
                  inputmode="text"
                  autocapitalize="characters"
                  autocomplete="off"
                  spellcheck="false"
                  placeholder="ABC-123"
                  @input="ticket = ($event.target as HTMLInputElement).value.toUpperCase()"
                />
                <span v-if="errTicket" class="warn">{{ errTicket }}</span>
                <span v-else-if="ramaTicket" class="hint">Claude va a leer el ticket y seguir el flujo de tickets del kit de trabajo.</span>
              </label>

              <label class="field">
                <span>{{ ramaTicket ? 'Nota para Claude' : 'Qué hay que hacer' }}</span>
                <textarea
                  v-model="tarea"
                  class="tarea"
                  rows="5"
                  :maxlength="ramaTicket ? MAX_NOTA_TICKET : MAX_TAREA"
                  :placeholder="ramaTicket ? `Nota para Claude (opcional). ${atajoTexto} para abrirla.` : `Contale a Claude la tarea. ${atajoTexto} para abrirla.`"
                  spellcheck="true"
                  @keydown="onTareaKeydown"
                />
                <span v-if="errTarea" class="warn">{{ errTarea }}</span>
              </label>

              <details class="mas" :open="masOpciones" @toggle="masOpciones = ($event.target as HTMLDetailsElement).open">
                <summary>Más opciones</summary>
                <label class="field">
                  <span>Nombre de la pestaña <i>(opcional)</i></span>
                  <input v-model="nombre" maxlength="60" placeholder="Las primeras palabras de la tarea" autocomplete="off" spellcheck="false" />
                  <span v-if="errNombre" class="warn">{{ errNombre }}</span>
                </label>
                <label class="field">
                  <span>Rama <i>(opcional)</i></span>
                  <input v-if="ramaTicket" class="rama" :value="ramaTicket" disabled autocomplete="off" spellcheck="false" />
                  <input v-else v-model="rama" class="rama" maxlength="80" placeholder="Se arma sola, p. ej. feature/mi-tarea" autocomplete="off" spellcheck="false" />
                  <span v-if="errRama" class="warn">{{ errRama }}</span>
                </label>
                <p class="hint">Se crea una copia del repo al lado, con su propia rama, y Claude trabaja ahí.</p>
              </details>
            </template>

            <template v-else>

            <label v-if="mostrarBuscador" class="field">
              <span>Buscar</span>
              <input v-model="busqueda" type="search" autocomplete="off" spellcheck="false" placeholder="Nombre o ruta" />
            </label>

            <div class="field">
              <span>Carpeta</span>
              <div v-if="cargando" class="st"><span class="spin" aria-hidden="true" /> Cargando…</div>
              <div v-else class="pick" role="listbox" aria-label="Carpeta">
                <button
                  v-for="c in listado"
                  :key="c.ruta"
                  type="button"
                  class="carp"
                  :class="{ on: carpetaRuta === c.ruta }"
                  :aria-pressed="carpetaRuta === c.ruta"
                  @click="carpetaRuta = c.ruta"
                >
                  <span class="nom">{{ c.nombre }}</span>
                  <span class="ruta mono">{{ c.ruta }}</span>
                </button>
              </div>
            </div>

            <div class="field">
              <span>Tipo</span>
              <span class="seg" role="group" aria-label="Tipo de terminal">
                <button type="button" :aria-pressed="tipo === 'shell'" @click="tipo = 'shell'">Terminal</button>
                <button type="button" :aria-pressed="tipo === 'claude'" @click="tipo = 'claude'">Claude</button>
              </span>
            </div>

            <label class="field">
              <span>Nombre <i>(opcional)</i></span>
              <input v-model="nombre" maxlength="60" :placeholder="phNombre" autocomplete="off" spellcheck="false" />
              <span v-if="errNombre" class="warn">{{ errNombre }}</span>
            </label>
            </template>

            <section v-if="pideConfianza" class="conf" role="alertdialog" aria-labelledby="nt-conf" aria-describedby="nt-conf-d">
              <h3 id="nt-conf" class="conf-t"><Icon name="warn" :size="14" /> Este repo prepara la copia</h3>
              <p id="nt-conf-d" class="hint">Antes de abrir la tarea, mirá qué va a hacer. Si confiás, se guarda para este contenido exacto: si cambia, te lo vuelvo a preguntar.</p>
              <p v-if="pideConfianza.copiar.length" class="hint">Copia estos archivos ignorados: <span class="mono">{{ pideConfianza.copiar.join(', ') }}</span></p>
              <p v-if="pideConfianza.puertos" class="hint">Reserva {{ pideConfianza.puertos }} {{ pideConfianza.puertos === 1 ? 'puerto' : 'puertos' }} para la copia.</p>
              <span class="conf-n">setup.toml</span>
              <pre class="conf-pre mono" tabindex="0">{{ pideConfianza.setup_toml }}</pre>
              <template v-if="pideConfianza.script">
                <span class="conf-n">{{ pideConfianza.script }} (se corre en una terminal de la copia)</span>
                <pre class="conf-pre mono" tabindex="0">{{ pideConfianza.script_contenido }}</pre>
              </template>
              <div class="actions">
                <button type="button" class="btn btn-primary" :disabled="abriendo" @click="confiarYAbrir">Confiar y abrir</button>
                <button type="button" class="btn btn-ghost" :disabled="abriendo" @click="noConfiar">Cancelar</button>
              </div>
            </section>

            <p v-if="avisoPuertos" class="hint" role="status">Con docker compose, los puertos son fijos: una copia corriendo a la vez.</p>

            <p v-if="error" class="problem" role="alert"><Icon name="warn" :size="14" /> <span>{{ error }}</span></p>

            <div class="sheet-actions actions">
              <button type="submit" class="btn btn-primary" :class="{ spinning: abriendo }" :disabled="!listo" :aria-busy="abriendo">
                <span v-if="abriendo" class="spin" aria-hidden="true" />{{ abriendo ? 'Abriendo…' : modo === 'tarea' ? 'Abrir tarea' : 'Abrir' }}
              </button>
              <button type="button" class="btn btn-ghost" :disabled="abriendo" @click="emit('close')">Cancelar</button>
            </div>
          </div>
          <ListoOverlay :visible="listoPantalla" :texto="listoTxt" />
        </form>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cs { z-index: 60; }
.cs-panel { position: relative; max-height: 94dvh; touch-action: pan-y; }
.cs-stagger { gap: 14px; }
.title { display: flex; align-items: center; gap: 8px; }
.title :deep(svg) { color: var(--accent); }
.field { display: grid; gap: 6px; min-width: 0; }
.field > span { font-size: 12px; font-weight: 600; color: var(--text-3); }
.field i { font-style: normal; font-weight: 500; color: var(--text-4); }
input,
.sel { width: 100%; min-width: 0; height: 44px; padding: 0 12px; border-radius: 12px; font: inherit; font-size: 14px; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; }
input.ticket { font-size: 16px; text-transform: uppercase; }
input:disabled { color: var(--text-3); opacity: 0.8; }
input:focus,
.sel:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.pick { display: grid; gap: 6px; max-height: min(40dvh, 280px); overflow-y: auto; }
.carp { display: grid; gap: 2px; text-align: left; padding: 10px 12px; border-radius: 12px; font: inherit; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); cursor: pointer; transition: background 0.2s, box-shadow 0.2s; }
.carp.on { color: var(--text); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.nom { font-size: 14px; font-weight: 600; }
.ruta { font-size: 12px; color: var(--text-4); }
.seg { display: inline-flex; padding: 2px; gap: 2px; border-radius: var(--r-md); background: var(--bg-2); border: 1px solid var(--line-2); }
.seg button { padding: 6px 14px; border: 0; border-radius: 7px; font: inherit; font-size: 13px; font-weight: 600; color: var(--text-3); background: transparent; cursor: pointer; }
.seg button[aria-pressed='true'] { color: var(--text); background: var(--surface); box-shadow: 0 1px 2px rgb(0 0 0 / 0.12); }
.modo { justify-self: start; }
.tarea { width: 100%; min-width: 0; padding: 10px 12px; border-radius: 12px; font: inherit; font-size: 14px; line-height: 1.4; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; resize: vertical; min-height: 110px; }
.tarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.mas { display: grid; gap: 12px; }
.mas summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--text-3); }
.mas[open] summary { margin-bottom: 4px; }
.hint { margin: 0; font-size: 12px; color: var(--text-4); }
.st { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-3); }
.warn { font-size: 12px; color: var(--st-blocked); }
.problem { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 9px 12px; border-radius: var(--r-md); font-size: 13px; color: var(--danger); background: var(--danger-soft); border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent); }
.conf { display: grid; gap: 8px; padding: 12px; border-radius: var(--r-md); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--accent-line); min-width: 0; }
.conf-t { display: flex; align-items: center; gap: 6px; margin: 0; font-size: 14px; }
.conf-n { font-size: 12px; font-weight: 600; color: var(--text-3); overflow-wrap: anywhere; }
.conf-pre { margin: 0; padding: 10px 12px; max-height: 30dvh; overflow: auto; overscroll-behavior: contain; border-radius: 12px; font-size: 12px; line-height: 1.45; color: var(--text-2); background: var(--bg-2); border: 1px solid var(--line-2); white-space: pre-wrap; overflow-wrap: anywhere; }
.actions { display: flex; flex-direction: column-reverse; gap: 8px; }
@media (min-width: 640px) { .actions .btn { flex: 1; } }
</style>
