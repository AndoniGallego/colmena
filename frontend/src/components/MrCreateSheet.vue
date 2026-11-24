<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { useKeyboard } from '../lib/keyboard'
import { ApiError } from '../api/types'
import type { CrearOpciones, MrPersona, RamaInfo } from '../api/mrsApi'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { useListoPanel } from '../lib/listoPanel'
import { cargarMrs, irAMr, mrsApi } from '../state/mrs'
import Icon from './Icon.vue'
import ListoOverlay from './ListoOverlay.vue'
import { renderGitlabMarkdown } from '../lib/gitlabMarkdown'

const props = defineProps<{ open: boolean; sessionId?: string | null }>()
const emit = defineEmits<{ close: [] }>()
const { run } = useGsap()
const kb = useKeyboard()
const panel = ref<HTMLElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => props.open, { onEscape: () => emit('close') })
useSheetSwipe(panel, () => emit('close'))
const layout = computed(() => (kb.open.value && kb.height.value ? { height: `${kb.height.value}px`, top: `${kb.top.value}px` } : undefined))

const opciones = ref<CrearOpciones | null>(null)
const cargando = ref(false)
const error = ref('')
const repo = ref('')
const rama = ref('')
const target = ref('')
const titulo = ref('')
const vistaPrevia = ref(false)
const descripcion = ref('')
const reviewers = ref(new Set<string>())
const info = ref<RamaInfo | null>(null)
const chequeando = ref(false)
const redactando = ref(false)
const creando = ref(false)
const cierre = () => emit('close')
const { listo: listoPantalla, listoTxt, mostrarListo } = useListoPanel(cierre)

const equipo = computed<MrPersona[]>(() => opciones.value?.equipo ?? [])
const repoSel = computed(() => opciones.value?.repos.find((r) => r.path === repo.value) ?? null)
const ramas = computed(() => {
  const r = repoSel.value
  if (!r) return []
  return r.ramas.includes(rama.value) || !rama.value ? r.ramas : [rama.value, ...r.ramas]
})
const listo = computed(() => !!info.value?.pusheada && !info.value.existente && !!titulo.value.trim() && !!target.value.trim() && target.value !== rama.value)

const msg = (e: unknown, f: string) => (e instanceof ApiError ? e.message : f)

watch(
  () => props.open,
  async (on) => {
    if (!on) return
    error.value = ''
    titulo.value = descripcion.value = ''
    vistaPrevia.value = false
    reviewers.value = new Set()
    info.value = null
    cargando.value = true
    try {
      const o = await mrsApi().opciones(props.sessionId ?? undefined)
      opciones.value = o
      const r = o.repos.find((x) => x.path === o.sugerido.repo) ?? o.repos[0]
      repo.value = r?.path ?? ''
      rama.value = (r && r.path === o.sugerido.repo && o.sugerido.rama) || r?.rama || ''
    } catch (e) {
      error.value = msg(e, 'No pude leer tus repos')
    } finally {
      cargando.value = false
    }
  },
)

watch(repo, (p, o) => {
  if (o && p !== o) rama.value = repoSel.value?.rama ?? ''
})

let seq = 0
watch([repo, rama], async ([r, b]) => {
  info.value = null
  target.value = ''
  if (!r || !b || !props.open) return
  const mine = ++seq
  chequeando.value = true
  try {
    const i = await mrsApi().rama(r, b)
    if (mine !== seq) return
    info.value = i
    target.value = i.target
  } catch (e) {
    if (mine === seq) error.value = msg(e, 'No pude revisar la rama')
  } finally {
    if (mine === seq) chequeando.value = false
  }
})

function toggleReviewer(u: string) {
  haptic(4)
  const s = new Set(reviewers.value)
  if (!s.delete(u)) s.add(u)
  reviewers.value = s
}

async function redactar() {
  if (redactando.value || !info.value?.pusheada || !target.value) return
  haptic(6)
  redactando.value = true
  error.value = ''
  try {
    const out = await mrsApi().redactar(repo.value, rama.value, target.value)
    if (out.titulo) titulo.value = out.titulo
    if (out.descripcion) descripcion.value = out.descripcion
  } catch (e) {
    error.value = msg(e, 'Claude no pudo redactarlo')
  } finally {
    redactando.value = false
  }
}

async function crear() {
  if (!listo.value || creando.value) return
  haptic([8, 30, 8])
  creando.value = true
  error.value = ''
  try {
    const out = await mrsApi().crear({
      repo: repo.value,
      rama: rama.value,
      target: target.value.trim(),
      titulo: titulo.value.trim(),
      descripcion: descripcion.value,
      reviewers: [...reviewers.value],
      session_id: props.sessionId ?? undefined,
    })
    mostrarListo('MR creado')
    await cargarMrs(true)
    if (out.ref) irAMr(out.ref)
  } catch (e) {
    error.value = msg(e, 'GitLab no respondió')
  } finally {
    creando.value = false
  }
}

function onEnter(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(el.querySelector('.sheet-scrim'), { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0)
    tl.fromTo(el.querySelector('.cs-panel'), { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    tl.from(el.querySelectorAll('.cs-stagger > *'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', stagger: 0.04 }, 0.15)
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
        <form ref="panel" class="sheet-panel cs-panel" role="dialog" aria-modal="true" aria-labelledby="mrc-title" @submit.prevent="crear">
          <i class="sheet-grip grip" aria-hidden="true" />
          <div class="sheet-stagger cs-stagger">
            <h2 id="mrc-title" class="sheet-title title"><Icon name="merge" :size="18" /> Nuevo MR</h2>

            <div class="two">
              <label class="field">
                <span>Repo</span>
                <select v-model="repo" :disabled="cargando || !opciones?.repos.length">
                  <option v-if="cargando" value="">Buscando repos…</option>
                  <option v-for="r in opciones?.repos ?? []" :key="r.path" :value="r.path">{{ r.nombre }}</option>
                </select>
              </label>
              <label class="field">
                <span>Rama</span>
                <select v-model="rama" :disabled="!repoSel">
                  <option v-for="b in ramas" :key="b" :value="b">{{ b }}</option>
                </select>
              </label>
            </div>

            <div class="estado" aria-live="polite">
              <span v-if="chequeando" class="st"><span class="spin" aria-hidden="true" /> Revisando la rama en GitLab…</span>
              <span v-else-if="info && !info.pusheada" class="st warn"><Icon name="warn" :size="14" /> La rama no está en GitLab, pusheala primero</span>
              <span v-else-if="info?.existente" class="st warn">
                <Icon name="merge" :size="14" /> Ya hay un MR abierto para esta rama
                <button type="button" class="link" @click="(emit('close'), irAMr(info.existente.ref))">Ver !{{ info.existente.iid }}</button>
              </span>
              <span v-else-if="info" class="st ok"><Icon name="check" :size="14" /> Rama en GitLab</span>
            </div>

            <label class="field">
              <span>Hacia</span>
              <input v-model="target" class="mono" maxlength="200" autocomplete="off" spellcheck="false" placeholder="develop" :disabled="!info?.pusheada" />
            </label>

            <div class="field">
              <span>Reviewers <i>(vos quedás como assignee)</i></span>
              <div class="pick">
                <button v-for="e in equipo" :key="e.username" type="button" class="person" :class="{ on: reviewers.has(e.username) }" :aria-pressed="reviewers.has(e.username)" @click="toggleReviewer(e.username)">
                  <Icon v-if="reviewers.has(e.username)" name="check" :size="12" /> {{ e.nombre }}
                </button>
              </div>
            </div>

            <div class="field">
              <span class="lh">
                Título
                <button type="button" class="ai" :class="{ busy: redactando, 'sk-sweep': redactando }" :disabled="redactando || !info?.pusheada || !target" @click="redactar">
                  <span v-if="redactando" class="spin" aria-hidden="true" /><Icon v-else name="sparkle" :size="14" /> {{ redactando ? 'Redactando…' : 'Redactar con Claude' }}
                </button>
              </span>
              <input v-model="titulo" maxlength="255" placeholder="feat: …" aria-label="Título" />
            </div>
            <div class="field">
              <span class="lh">
                <span id="mrc-desc">Descripción</span>
                <span class="seg" role="group" aria-label="Modo de la descripción">
                  <button type="button" :aria-pressed="!vistaPrevia" @click="vistaPrevia = false">Escribir</button>
                  <button type="button" :aria-pressed="vistaPrevia" :disabled="!descripcion.trim()" @click="vistaPrevia = true">Vista previa</button>
                </span>
              </span>
              <div v-if="vistaPrevia && descripcion.trim()" class="md preview" aria-labelledby="mrc-desc" v-html="renderGitlabMarkdown(descripcion, null)" />
              <textarea v-else v-model="descripcion" rows="6" maxlength="20000" placeholder="Qué cambia y por qué (acepta Markdown)" aria-labelledby="mrc-desc" />
            </div>

            <p v-if="error" class="problem" role="alert"><Icon name="warn" :size="14" /> <span>{{ error }}</span></p>

            <div class="sheet-actions actions">
              <button type="submit" class="btn btn-primary" :class="{ spinning: creando }" :disabled="!listo || creando" :aria-busy="creando">
                <span v-if="creando" class="spin" aria-hidden="true" />{{ creando ? 'Creando…' : 'Crear MR' }}
              </button>
              <button type="button" class="btn btn-ghost" :disabled="creando" @click="emit('close')">Cancelar</button>
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
.cs-panel { position: relative; width: min(100%, 620px); max-height: 94dvh; overflow-x: hidden; touch-action: pan-y; }
@media (min-width: 640px) {
  .two { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
}
.cs-stagger { grid-template-columns: minmax(0, 1fr); gap: 14px; }
.seg { display: inline-flex; padding: 2px; gap: 2px; border-radius: var(--r-md); background: var(--bg-2); border: 1px solid var(--line-2); }
.seg button { padding: 3px 9px; border: 0; border-radius: 7px; font: inherit; font-size: var(--t-sm); font-weight: 600; color: var(--text-3); background: transparent; cursor: pointer; }
.seg button[aria-pressed='true'] { color: var(--text); background: var(--surface); box-shadow: 0 1px 2px rgb(0 0 0 / 0.12); }
.seg button:disabled { opacity: 0.45; cursor: default; }
.preview { min-height: 140px; max-height: 46dvh; overflow: auto; overflow-x: hidden; padding: 10px 12px; border-radius: 12px; font-size: 14px; background: var(--bg-2); border: 1px solid var(--line-2); }
.preview :deep(.md-code), .preview :deep(.md-table) { contain: inline-size; }
.title { display: flex; align-items: center; gap: 8px; margin: 0; font-family: var(--font-display); font-size: 20px; font-weight: 600; letter-spacing: -0.02em; }
.title :deep(svg) { color: var(--accent); }
.two { display: grid; gap: 14px; }
.field { display: grid; gap: 6px; min-width: 0; }
.field > span { font-size: 12px; font-weight: 600; color: var(--text-3); }
.field i { font-style: normal; font-weight: 500; color: var(--text-4); }
.lh { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
select, input, textarea { width: 100%; min-width: 0; padding: 0 12px; border-radius: 12px; font: inherit; font-size: 14px; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; transition: border-color 0.2s, box-shadow 0.25s, opacity 0.2s; }
select, input { height: 44px; }
input.mono { font-size: 13px; }
textarea { padding: 10px 12px; line-height: 1.45; resize: vertical; }
select:focus, input:focus, textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
select:disabled, input:disabled { opacity: 0.55; }
.estado { min-height: 20px; margin-top: -6px; }
.st { display: inline-flex; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 13px; font-weight: 560; color: var(--text-3); }
.st.warn { color: var(--st-blocked); }
.st.ok { color: var(--st-done); }
.link { font-size: var(--t-md); font-weight: 600; color: var(--accent); }
.pick { display: flex; flex-wrap: wrap; gap: 6px; }
.person { display: inline-flex; align-items: center; gap: 5px; height: 34px; padding: 0 12px; border-radius: var(--r-pill); font-size: 13px; font-weight: 540; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), box-shadow 0.25s; }
.person:active { scale: var(--press-scale); }
.person.on { color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.ai { display: inline-flex; align-items: center; gap: 6px; height: 30px; padding: 0 11px; border-radius: var(--r-pill); font-size: var(--t-md); font-weight: 600; color: var(--accent); background: var(--accent-soft); transition: filter 0.2s, scale 0.3s var(--spring), opacity 0.2s; }
.ai:hover:not(:disabled) { filter: brightness(1.12); }
.ai:active:not(:disabled) { scale: var(--press-scale); }
.ai:disabled:not(.busy) { opacity: 0.45; cursor: default; }
.ai.busy { --sk-bg: linear-gradient(90deg, transparent, color-mix(in srgb, var(--accent) 25%, transparent), transparent); --sk-left: -25%; --sk-w: 50%; --sk-tile: 100%; --sk-dx: 200%; --sk-dur: 1.1s; }
.problem { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 9px 12px; border-radius: var(--r-md); font-size: 13px; line-height: 1.4; color: var(--danger); background: var(--danger-soft); border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent); }
.problem :deep(svg) { flex: none; margin-top: 2px; }
@media (min-width: 640px) { .actions .btn { flex: 1; } }
:root[data-motion='soft'] .ai.busy::after { animation: none; }
</style>
