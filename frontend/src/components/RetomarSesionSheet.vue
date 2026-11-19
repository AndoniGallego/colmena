<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { useKeyboard } from '../lib/keyboard'
import { ApiError } from '../api/types'
import { getSesionesViejas, getTerminalesCarpetas, postSesionesViejasRetomar, showOnBoard } from '../state/app'
import {
  armarCuerpoRetomar,
  filtrarSesionesViejas,
  idOperacionRetomar,
  mensajeErrorRetomar,
  type SesionVieja,
} from '../lib/retomarSesion'
import { validarNombreNueva, type GrupoItem as GrupoTablero } from '../lib/nuevaTerminal'
import { ago, useNow } from '../lib/time'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { run } = useGsap()
const panel = ref<HTMLElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => props.open, { onEscape: () => emit('close') })
useSheetSwipe(panel, () => emit('close'))
const now = useNow()
const kb = useKeyboard()
const layout = computed(() => (kb.open.value && kb.height.value ? { height: `${kb.height.value}px`, top: `${kb.top.value}px` } : undefined))

const paso = ref<'lista' | 'detalle' | 'ok'>('lista')
const sesiones = ref<SesionVieja[]>([])
const sel = ref<SesionVieja | null>(null)
const grupos = ref<GrupoTablero[]>([])
const busqueda = ref('')
const grupoId = ref('')
const nombre = ref('')
const nombreTarjeta = ref('')
const cargando = ref(false)
const enviando = ref(false)
const error = ref('')
const opId = ref('')
const paneNuevo = ref('')

const listado = computed(() => filtrarSesionesViejas(sesiones.value, busqueda.value))
const mostrarBuscador = computed(() => sesiones.value.length > 6)
const mostrarGrupos = computed(() => grupos.value.length > 0)
const errNombre = computed(() => validarNombreNueva(nombre.value))
const listo = computed(() => !!sel.value && !errNombre.value && !enviando.value)

const msg = (e: unknown, fallback: string) =>
  e instanceof ApiError ? mensajeErrorRetomar(e.status, e.message) || e.message : fallback

watch(
  () => props.open,
  async (on) => {
    if (!on) return
    paso.value = 'lista'
    sel.value = null
    busqueda.value = nombre.value = nombreTarjeta.value = ''
    grupoId.value = ''
    paneNuevo.value = ''
    error.value = ''
    opId.value = idOperacionRetomar()
    cargando.value = true
    try {
      const [lista, carpetas] = await Promise.all([getSesionesViejas(''), getTerminalesCarpetas()])
      sesiones.value = Array.isArray(lista) ? lista : []
      grupos.value = carpetas.grupos ?? []
    } catch (e) {
      error.value = msg(e, 'No pude cargar las sesiones')
    } finally {
      cargando.value = false
    }
  },
)

function elegir(s: SesionVieja) {
  sel.value = s
  nombre.value = s.titulo.slice(0, 60)
  nombreTarjeta.value = s.titulo.slice(0, 60)
  paso.value = 'detalle'
  error.value = ''
}

async function retomar() {
  if (!listo.value || !sel.value) return
  haptic([8, 30, 8])
  const body = armarCuerpoRetomar(sel.value, nombre.value, grupoId.value, nombreTarjeta.value, opId.value)
  if (!body) {
    error.value = 'Revisá el nombre'
    return
  }
  enviando.value = true
  error.value = ''
  try {
    const out = await postSesionesViejasRetomar(body)
    paneNuevo.value = out.pane_id || out.sesion_id
    paso.value = 'ok'
  } catch (e) {
    error.value = msg(e, 'No pude retomarla')
  } finally {
    enviando.value = false
  }
}

function irAlTablero() {
  if (paneNuevo.value) showOnBoard(paneNuevo.value)
  emit('close')
}

function volver() {
  if (enviando.value) return
  paso.value = 'lista'
  sel.value = null
}

function onEnter(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(el.querySelector('.sheet-scrim'), { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0)
    tl.fromTo(el.querySelector('.rs-panel'), { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
  })
}
function onLeave(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.to(el.querySelector('.sheet-scrim'), { opacity: 0, duration: 0.22 }, 0)
    tl.to(el.querySelector('.rs-panel'), { yPercent: 100, duration: 0.3, ease: 'power3.in' }, 0)
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="onEnter" @leave="onLeave">
      <div v-if="open" class="sheet-root rs" :style="layout" @keydown="onKeydown">
        <div class="sheet-scrim rs-back" @click="emit('close')" />
        <form v-if="paso !== 'ok'" ref="panel" class="sheet-panel rs-panel" role="dialog" aria-modal="true" aria-labelledby="rs-title" @submit.prevent="retomar">
          <i class="sheet-grip grip" aria-hidden="true" />
          <div class="sheet-stagger rs-stagger">
            <h2 id="rs-title" class="sheet-title title"><Icon name="clock" :size="18" /> Retomar sesión</h2>

            <template v-if="paso === 'lista'">
              <label v-if="mostrarBuscador" class="field">
                <span>Buscar</span>
                <input v-model="busqueda" type="search" autocomplete="off" spellcheck="false" placeholder="Título, carpeta o frase" />
              </label>
              <div v-if="cargando" class="st"><span class="spin" aria-hidden="true" /> Cargando…</div>
              <ul v-else class="lista" role="list">
                <li v-for="s in listado" :key="s.session_id">
                  <button type="button" class="fila" @click="elegir(s)">
                    <span class="fila-top">
                      <strong class="fila-tit">{{ s.titulo }}</strong>
                      <span class="fila-ago">{{ ago(s.ultimo_ts, now) }}</span>
                    </span>
                    <span class="fila-carp mono" :title="s.carpeta">{{ s.carpeta }}</span>
                    <span class="fila-frase">{{ s.ultima_frase }}</span>
                  </button>
                </li>
              </ul>
              <p v-if="!cargando && !listado.length" class="vacío">No hay sesiones para retomar en los últimos 30 días.</p>
            </template>

            <template v-else>
              <p class="sub">Sesión: <b>{{ sel?.titulo }}</b></p>
              <p class="sub mono carp" :title="sel?.carpeta">{{ sel?.carpeta }}</p>

              <label v-if="mostrarGrupos" class="field">
                <span>Destino</span>
                <select v-model="grupoId" class="sel">
                  <option value="">Tarjeta nueva</option>
                  <option v-for="g in grupos" :key="g.id" :value="g.id">{{ g.nombre }}</option>
                </select>
              </label>

              <label v-if="!grupoId" class="field">
                <span>Nombre de la tarjeta</span>
                <input v-model="nombreTarjeta" maxlength="60" autocomplete="off" spellcheck="false" />
              </label>

              <label class="field">
                <span>Nombre de la pestaña</span>
                <input v-model="nombre" maxlength="60" autocomplete="off" spellcheck="false" />
                <span v-if="errNombre" class="warn">{{ errNombre }}</span>
              </label>
            </template>

            <p v-if="error" class="problem" role="alert"><Icon name="warn" :size="14" /> <span>{{ error }}</span></p>

            <div class="sheet-actions actions">
              <button v-if="paso === 'detalle'" type="submit" class="btn btn-primary" :class="{ spinning: enviando }" :disabled="!listo" :aria-busy="enviando">
                <span v-if="enviando" class="spin" aria-hidden="true" />{{ enviando ? 'Retomando…' : 'Retomar' }}
              </button>
              <button v-if="paso === 'detalle'" type="button" class="btn btn-ghost" :disabled="enviando" @click="volver">Volver</button>
              <button type="button" class="btn btn-ghost" :disabled="enviando" @click="emit('close')">Cerrar</button>
            </div>
          </div>
        </form>

        <div v-else ref="panel" class="sheet-panel rs-panel" role="dialog" aria-modal="true" aria-labelledby="rs-ok">
          <h2 id="rs-ok" class="sheet-title title">Listo</h2>
          <p class="sub">La sesión quedó abierta en el tablero.</p>
          <div class="sheet-actions actions">
            <button type="button" class="btn btn-primary" @click="irAlTablero">Ver en el tablero</button>
            <button type="button" class="btn btn-ghost" @click="emit('close')">Cerrar</button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.rs { z-index: 60; }
.rs-panel { max-height: 94dvh; touch-action: pan-y; }
.rs-stagger { gap: 14px; }
.title { display: flex; align-items: center; gap: 8px; }
.title :deep(svg) { color: var(--accent); }
.field { display: grid; gap: 6px; min-width: 0; }
.field > span { font-size: 12px; font-weight: 600; color: var(--text-3); }
input,
.sel { width: 100%; min-width: 0; height: 44px; padding: 0 12px; border-radius: 12px; font: inherit; font-size: 14px; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; }
input:focus,
.sel:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.lista { list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; max-height: min(50dvh, 360px); overflow-y: auto; }
.fila { width: 100%; text-align: left; display: grid; gap: 4px; padding: 12px; border-radius: 12px; border: 1px solid var(--line); background: var(--surface-2); font: inherit; color: var(--text-2); cursor: pointer; transition: background 0.2s, border-color 0.2s; }
.fila:hover { border-color: color-mix(in srgb, var(--accent) 40%, transparent); color: var(--text); }
.fila-top { display: flex; justify-content: space-between; gap: 8px; align-items: baseline; }
.fila-tit { font-size: 14px; color: var(--text); }
.fila-ago { font-size: 12px; color: var(--text-4); flex-shrink: 0; }
.fila-carp { font-size: 11px; color: var(--text-4); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.fila-frase { font-size: 13px; color: var(--text-3); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.sub { margin: 0; font-size: 13px; color: var(--text-3); }
.carp { font-size: 12px; }
.st { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; color: var(--text-3); }
.vacío { font-size: 13px; color: var(--text-3); margin: 0; }
.warn { font-size: 12px; color: var(--st-blocked); }
.problem { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 9px 12px; border-radius: var(--r-md); font-size: 13px; color: var(--danger); background: var(--danger-soft); border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent); }
.actions { display: flex; flex-direction: column-reverse; gap: 8px; }
@media (min-width: 640px) { .actions .btn { flex: 1; } }
</style>
