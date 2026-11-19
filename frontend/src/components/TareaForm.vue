<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { getCarpetasRepo, type CarpetaRepo, type Programa } from '../api/programadasApi'
import { useFocusTrap } from '../lib/focusTrap'
import { useKeyboard } from '../lib/keyboard'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { mensajeError } from '../lib/errores'
import { armarCuerpoPrograma, DIAS_CORTOS, DIAS_LETRA, MAX_NOMBRE, MAX_PEDIDO, validarPrograma, type Agente, type FormPrograma, type TipoCuando } from '../lib/tareas'
import { guardar, tareas } from '../state/tareas'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import SegControl from './SegControl.vue'

const props = defineProps<{ open: boolean; programa: Programa | null; cursorDisponible: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { run } = useGsap()
const kb = useKeyboard()
const panel = ref<HTMLElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => props.open, { onEscape: () => emit('close') })
useSheetSwipe(panel, () => emit('close'))
const layout = computed(() => (kb.open.value && kb.height.value ? { height: `${kb.height.value}px`, top: `${kb.top.value}px` } : undefined))

const vacio = (): FormPrograma => ({ nombre: '', repo: '', pedido: '', agente: 'claude', modelo: '', tipo: 'diaria', hora: '09:00', dias: [0, 1, 2, 3, 4], dia: 0 })
const f = ref<FormPrograma>(vacio())
const repos = ref<CarpetaRepo[]>([])
const cargandoRepos = ref(false)
const errorRepos = ref('')
const aviso = ref('')

const editando = computed(() => props.programa !== null)
const motivo = computed(() => validarPrograma(f.value, props.cursorDisponible))

watch(
  () => props.open,
  async (abierto) => {
    if (!abierto) return
    aviso.value = ''
    tareas.errorForm = ''
    const p = props.programa
    f.value = p
      ? { nombre: p.nombre, repo: p.repo, pedido: p.pedido, agente: p.agente, modelo: p.modelo, tipo: p.cuando.tipo, hora: p.cuando.hora, dias: [...(p.cuando.dias ?? [])], dia: p.cuando.dia ?? 0 }
      : vacio()
    cargandoRepos.value = true
    errorRepos.value = ''
    try {
      repos.value = await getCarpetasRepo()
    } catch (e) {
      errorRepos.value = mensajeError(e, 'No pude leer los repos.')
    } finally {
      cargandoRepos.value = false
    }
  },
  { immediate: true },
)

function alternarDia(d: number) {
  const s = new Set(f.value.dias)
  if (s.has(d)) s.delete(d)
  else s.add(d)
  f.value.dias = [...s].sort((a, b) => a - b)
}

const tiposCuando: { value: TipoCuando; label: string }[] = [
  { value: 'diaria', label: 'Todos los días' },
  { value: 'dias', label: 'Algunos días' },
  { value: 'semanal', label: 'Una vez por semana' },
]
const agentes = computed<{ value: Agente; label: string; disabled?: boolean }[]>(() => [
  { value: 'claude', label: 'Claude' },
  { value: 'cursor', label: 'Cursor', disabled: !props.cursorDisponible },
])

async function enviar() {
  aviso.value = ''
  if (motivo.value) {
    aviso.value = motivo.value
    return
  }
  if (await guardar(armarCuerpoPrograma(f.value), props.programa?.id)) emit('close')
}

function onEnter(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(el.querySelector('.sheet-scrim'), { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0)
    tl.fromTo(el.querySelector('.tf-panel'), { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
  })
}
function onLeave(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.to(el.querySelector('.sheet-scrim'), { opacity: 0, duration: 0.22 }, 0)
    tl.to(el.querySelector('.tf-panel'), { yPercent: 100, duration: 0.3, ease: 'power3.in' }, 0)
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="onEnter" @leave="onLeave">
      <div v-if="open" class="sheet-root tf" :style="layout" @keydown="onKeydown">
        <div class="sheet-scrim" @click="emit('close')" />
        <form ref="panel" class="sheet-panel tf-panel" role="dialog" aria-modal="true" aria-labelledby="tf-title" novalidate @submit.prevent="enviar">
          <i class="sheet-grip" aria-hidden="true" />
          <div class="sheet-stagger tf-stagger">
            <h2 id="tf-title" class="sheet-title tf-title"><Icon name="clock" :size="18" /> {{ editando ? 'Editar tarea' : 'Nueva tarea programada' }}</h2>

            <label class="field">
              <span>Nombre</span>
              <input v-model="f.nombre" type="text" :maxlength="MAX_NOMBRE" autocomplete="off" placeholder="Revisar MRs abiertos" data-test="nombre" />
            </label>

            <div class="field">
              <span>Repo</span>
              <p v-if="cargandoRepos" class="st">Cargando…</p>
              <p v-else-if="errorRepos" class="st err">{{ errorRepos }}</p>
              <p v-else-if="!repos.length && !f.repo" class="st">No hay repos de git entre las carpetas permitidas.</p>
              <div v-else class="pick" role="listbox" aria-label="Repo" data-test="repos">
                <button v-for="c in repos" :key="c.ruta" type="button" class="carp hit" :class="{ on: f.repo === c.ruta }" :aria-pressed="f.repo === c.ruta" @click="f.repo = c.ruta">
                  <span class="nom">{{ c.nombre }}</span>
                  <span class="ruta">{{ c.ruta }}</span>
                </button>
              </div>
            </div>

            <div class="field">
              <span>Quién lo hace</span>
              <SegControl v-model="f.agente" :options="agentes" label="Agente" />
              <p v-if="!cursorDisponible" class="hint">Cursor no está disponible en esta notebook.</p>
            </div>

            <label class="field">
              <span>Pedido <i>{{ f.pedido.length }}/{{ MAX_PEDIDO }}</i></span>
              <textarea v-model="f.pedido" class="pedido" :maxlength="MAX_PEDIDO" rows="5" placeholder="Qué tiene que hacer cada vez" data-test="pedido" />
            </label>

            <div class="field">
              <span>Cuándo</span>
              <SegControl v-model="f.tipo" :options="tiposCuando" label="Frecuencia" />
              <div v-if="f.tipo === 'dias'" class="dias" role="group" aria-label="Días">
                <button v-for="(l, d) in DIAS_LETRA" :key="d" type="button" class="dia hit" :aria-pressed="f.dias.includes(d)" :aria-label="DIAS_CORTOS[d]" @click="alternarDia(d)">{{ l }}</button>
              </div>
              <label v-if="f.tipo === 'semanal'" class="sub">
                <span>Día</span>
                <select v-model.number="f.dia" class="sel">
                  <option v-for="(n, d) in DIAS_CORTOS" :key="d" :value="d">{{ n }}</option>
                </select>
              </label>
              <label class="sub">
                <span>Hora</span>
                <input v-model="f.hora" type="time" class="hora" data-test="hora" />
              </label>
            </div>

            <details v-if="f.agente === 'cursor'" class="mas">
              <summary>Más opciones</summary>
              <label class="field">
                <span>Modelo de Cursor <i>(opcional)</i></span>
                <input v-model="f.modelo" type="text" autocomplete="off" spellcheck="false" placeholder="El que viene por defecto" />
              </label>
            </details>

            <p v-if="aviso || tareas.errorForm" class="problem" role="alert"><Icon name="warn" :size="14" /> <span>{{ tareas.errorForm || aviso }}</span></p>

            <div class="sheet-actions">
              <button type="submit" class="btn btn-primary" :class="{ spinning: tareas.guardando }" :aria-busy="tareas.guardando" :disabled="tareas.guardando" data-test="guardar">
                {{ tareas.guardando ? 'Guardando…' : editando ? 'Guardar' : 'Crear pausada' }}
              </button>
              <button type="button" class="btn btn-ghost" :disabled="tareas.guardando" @click="emit('close')">Cancelar</button>
            </div>
            <p v-if="!editando" class="hint">La tarea nace pausada: reanudala cuando quieras que empiece a correr.</p>
          </div>
        </form>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.tf { z-index: 90; }
.tf-panel { position: relative; max-height: 94dvh; touch-action: pan-y; }
.tf-stagger { gap: 14px; }
.tf-title { display: flex; align-items: center; gap: 8px; }
.tf-title :deep(svg) { color: var(--accent); }
.field { display: grid; gap: 6px; min-width: 0; }
.field > span { font-size: 12px; font-weight: 600; color: var(--text-3); }
.field i { font-style: normal; font-weight: 500; color: var(--text-4); }
input,
.sel,
.pedido { width: 100%; min-width: 0; box-sizing: border-box; font: inherit; font-size: 16px; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); border-radius: 12px; outline: none; }
input,
.sel { height: 44px; padding: 0 12px; }
.pedido { padding: 10px 12px; line-height: 1.4; resize: vertical; min-height: 110px; }
input:focus,
.sel:focus,
.pedido:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.pick { display: grid; gap: 6px; max-height: min(34dvh, 240px); overflow-y: auto; }
.carp { display: grid; gap: 2px; text-align: left; padding: 10px 12px; border-radius: 12px; font: inherit; color: var(--text-2); background: var(--surface-2); border: 0; box-shadow: inset 0 0 0 1px var(--line); cursor: pointer; min-width: 0; }
.carp.on { color: var(--text); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.nom { font-size: 14px; font-weight: 600; }
.ruta { font-size: 12px; color: var(--text-4); overflow-wrap: anywhere; }
.dias { display: flex; flex-wrap: wrap; gap: 6px; }
.dia { min-width: 40px; height: 40px; border-radius: 50%; border: 0; font: inherit; font-size: 14px; font-weight: 600; color: var(--text-3); background: var(--bg-2); box-shadow: inset 0 0 0 1px var(--line-2); cursor: pointer; }
.dia[aria-pressed='true'] { color: var(--text); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.sub { display: grid; grid-template-columns: 56px minmax(0, 1fr); align-items: center; gap: 8px; font-size: 13px; color: var(--text-3); }
.hora { max-width: 160px; }
.mas { display: grid; gap: 12px; }
.mas summary { cursor: pointer; font-size: 13px; font-weight: 600; color: var(--text-3); min-height: 44px; display: flex; align-items: center; }
.hint { margin: 0; font-size: 12px; color: var(--text-4); }
.st { margin: 0; font-size: 13px; color: var(--text-3); }
.st.err { color: var(--danger); }
.problem { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 9px 12px; border-radius: var(--r-md); font-size: 13px; color: var(--danger); background: var(--danger-soft); border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent); }
@media (pointer: coarse) { .dia { min-width: 44px; height: 44px; } }
</style>
