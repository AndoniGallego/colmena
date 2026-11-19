<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { DialogChoice } from '../api/types'
import { answered, canApprove, CHOICE_LABEL, dialogChanged, huellaOf, MAX_OTRO, needsPin, otroProblem, screenText, seleccionComplete, toolTitle } from '../lib/dialogo'
import { shortPath } from '../lib/transcript'
import { boardState } from '../state/app'
import PedidoCard from './PedidoCard.vue'
import { answerPermiso, answerPregunta, askPin, decidirPedido, dlg, loadDialog, resetDialog } from '../state/dialogo'
import { dialogoLink } from '../state/session'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'

const props = defineProps<{ sessionId: string; status: string; tabId?: string; vivo?: boolean }>()
const emit = defineEmits<{ vivo: [] }>()

const { run } = useGsap()
const card = ref<HTMLElement | null>(null)
const blocked = computed(() => props.status === 'blocked')
const view = computed(() => dlg.view)
const busy = computed(() => dlg.phase === 'sending' || dlg.phase === 'verifying')
const done = computed(() => dlg.phase === 'done')
const show = computed(() => !!view.value && view.value.tipo !== 'ninguno' && (blocked.value || done.value))
const permiso = computed(() => (view.value?.tipo === 'permiso' ? view.value.permiso : null))
const pedido = computed(() => (view.value?.tipo === 'pedido' ? view.value.pedido : null))
const pregunta = computed(() => (view.value?.tipo === 'pregunta' ? view.value.pregunta : null))
const pantalla = computed(() => (view.value?.tipo === 'desconocido' ? screenText(view.value.pantalla) : ''))

watch(
  () => [props.sessionId, blocked.value] as const,
  ([id, on]) => {
    if (!on) {
      if (dlg.phase !== 'done') resetDialog(id)
      return
    }
    if (dlg.sessionId !== id) resetDialog(id)
    void loadDialog(id)
  },
  { immediate: true },
)

let refreshTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => boardState.value.board,
  () => {
    if (!blocked.value || busy.value) return
    clearTimeout(refreshTimer)
    refreshTimer = setTimeout(() => void loadDialog(props.sessionId, { keepNotice: true }), 600)
  },
)
onBeforeUnmount(() => clearTimeout(refreshTimer))

// ---------- permission ----------
const changed = ref(false)
let changedTimer: ReturnType<typeof setTimeout> | undefined
onBeforeUnmount(() => clearTimeout(changedTimer))
const where = computed(() => (permiso.value?.herramienta === 'Bash' ? '' : shortPath(permiso.value?.archivo ?? '')))

const rule = computed(() => permiso.value?.regla ?? '')
const has = (c: DialogChoice) => !!permiso.value?.opciones.includes(c)
const can = (c: DialogChoice) => !!permiso.value && canApprove(permiso.value, c) && !busy.value && !done.value && !changed.value
const pending = ref<DialogChoice | null>(null)

function choose(c: DialogChoice) {
  if (!can(c)) return
  pending.value = c
  if (needsPin(c)) return askPin(c)
  void answerPermiso(c)
}
const label = (c: DialogChoice, base: string) => {
  if (pending.value !== c || !busy.value) return base
  return dlg.phase === 'verifying' ? 'Verificando…' : 'Enviando…'
}

// ---------- question ----------
const picks = ref<number[][]>([])
const step = ref(0)
const other = ref(false)
const text = ref('')
const input = ref<HTMLTextAreaElement | null>(null)
const qs = computed(() => pregunta.value?.preguntas ?? [])
const many = computed(() => qs.value.length > 1)
const summary = computed(() => many.value && step.value >= qs.value.length)
const cur = computed(() => qs.value[Math.min(step.value, qs.value.length - 1)])
const picksOf = (i: number) => picks.value[i] ?? []
const problem = computed(() => (other.value && text.value ? otroProblem(text.value) : null))
const stepReady = computed(() => (other.value ? !!text.value.trim() && !otroProblem(text.value) : !!cur.value && answered(cur.value, picks.value[step.value])))
const ready = computed(() => (many.value ? (summary.value ? !!pregunta.value && seleccionComplete(pregunta.value, picks.value) : stepReady.value) : stepReady.value))
const answerOf = (i: number) => picksOf(i).map((n) => qs.value[i].opciones[n].label).join(', ')

function pick(i: number) {
  if (busy.value || done.value || changed.value) return
  other.value = false
  const now = picksOf(step.value)
  const next = cur.value.multi ? (now.includes(i) ? now.filter((n) => n !== i) : [...now, i]) : [i]
  const all = [...picks.value]
  all[step.value] = next
  picks.value = all
}
async function pickOther() {
  if (busy.value || done.value) return
  other.value = true
  picks.value = []
  await nextTick()
  input.value?.focus()
}
function go(to: number) {
  if (busy.value || done.value) return
  step.value = Math.max(0, Math.min(qs.value.length, to))
}
function sendPregunta() {
  if (!ready.value || busy.value || changed.value) return
  if (many.value && !summary.value) return go(step.value + 1)
  void answerPregunta(other.value ? { otro: text.value } : { opciones: qs.value.map((_, i) => picksOf(i)) })
}

watch(
  () => huellaOf(view.value),
  (next, prev) => {
    picks.value = []
    step.value = 0
    other.value = false
    text.value = ''
    pending.value = null
    if (!dialogChanged(prev, next)) return
    changed.value = true
    clearTimeout(changedTimer)
    changedTimer = setTimeout(() => (changed.value = false), 1000)
  },
)

// ---------- unknown ----------
const screenOpen = ref(false)

// ---------- motion ----------
function onEnter(el: Element, finish: () => void) {
  if (isSoft() || dialogoLink.value) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.25, onComplete: finish }))
  run(() => {
    const tl = gsap.timeline({ onComplete: finish })
    tl.fromTo(el, { y: 26, scale: 0.95, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.8, ease: 'expo.out' })
    tl.from(el.querySelectorAll('.stagger > *'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', stagger: 0.05 }, 0.12)
  })
}
function onLeave(el: Element, finish: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: finish }))
  run(() => gsap.to(el, { y: -8, scale: 0.97, opacity: 0, height: 0, margin: 0, duration: 0.4, ease: 'power3.in', onComplete: finish }))
}

watch(done, (on) => {
  if (!on || !card.value || isSoft()) return
  run(() => gsap.fromTo(card.value, { scale: 1 }, { keyframes: { scale: [1, 1.025, 1] }, duration: 0.5, ease: 'power2.out' }))
})
watch(
  () => dlg.notice,
  (n) => {
    if (!n || !card.value || isSoft()) return
    run(() => gsap.fromTo(card.value, { x: 0 }, { keyframes: { x: [0, -6, 6, -3, 0] }, duration: 0.4, ease: 'none' }))
  },
)

// deep link from the push: scroll the card into view once it shows
watch(
  [show, card],
  async ([on, el]) => {
    if (!on || !el || !dialogoLink.value) return
    dialogoLink.value = false
    await nextTick()
    el.scrollIntoView({ block: 'center', behavior: isSoft() ? 'auto' : 'smooth' })
  },
  { flush: 'post' },
)
</script>

<template>
  <Transition :css="false" appear @enter="onEnter" @leave="onLeave">
    <section v-if="show" ref="card" class="dc" :data-kind="view?.tipo" :data-done="done" aria-label="Pedido de Claude Code" data-dialog>
      <i class="edge" aria-hidden="true" />
      <div class="stagger">
        <!-- pedido de permiso (ganchos) -->
        <PedidoCard
          v-if="pedido"
          :key="pedido.id"
          :pedido="pedido"
          :busy="busy"
          :done="done"
          :changed="changed"
          @permitir="(id) => void decidirPedido(id, 'permitir')"
          @rechazar="(id, m) => void decidirPedido(id, 'rechazar', m)"
          @siempre="() => askPin('siempre')"
        />

        <!-- permission -->
        <template v-else-if="permiso">
          <div class="top">
            <span class="kicker mono">permiso</span>
            <span class="tool mono">{{ permiso.herramienta }}</span>
            <span v-if="done" class="stamp mono"><Icon name="check" :size="12" /> Respondido</span>
          </div>
          <h2 class="title">{{ toolTitle(permiso) }}</h2>
          <p v-if="permiso.descripcion" class="desc">{{ permiso.descripcion }}</p>
          <p v-if="where" class="file mono" :title="permiso.archivo">{{ where }}<span v-if="permiso.replace_all"> · todas las apariciones</span></p>
          <pre v-if="permiso.detalle" class="code mono" tabindex="0">{{ permiso.detalle }}</pre>
          <p v-if="!permiso.completo" class="warn" role="alert"><Icon name="warn" :size="14" /> <span>Es demasiado largo para revisarlo acá. Miralo en la terminal antes de aprobar.</span></p>

          <div class="actions">
            <button v-if="has('si')" type="button" class="btn primary" :class="{ busy: busy && pending === 'si' }" :disabled="!can('si')" :aria-busy="busy && pending === 'si'" @click="choose('si')">
              <span v-if="busy && pending === 'si'" class="spin" aria-hidden="true" />{{ label('si', CHOICE_LABEL.si) }}
            </button>
            <button v-if="has('no')" type="button" class="btn ghost" :class="{ busy: busy && pending === 'no' }" :disabled="!can('no')" @click="choose('no')">
              <span v-if="busy && pending === 'no'" class="spin" aria-hidden="true" />{{ label('no', CHOICE_LABEL.no) }}
            </button>
            <button v-if="has('si_siempre')" type="button" class="btn always" :disabled="!can('si_siempre')" @click="choose('si_siempre')">
              <Icon name="lock" :size="13" /> {{ CHOICE_LABEL.si_siempre }}
            </button>
          </div>
          <p v-if="has('si_siempre') && rule" class="rule mono">Guarda la regla <b>{{ rule }}</b></p>
          <div v-if="has('si_auto') || has('si_ediciones')" class="actions">
            <button v-if="has('si_auto')" type="button" class="btn mode" :disabled="!can('si_auto')" @click="choose('si_auto')">
              <Icon name="warn" :size="14" /> {{ CHOICE_LABEL.si_auto }}
            </button>
            <button v-if="has('si_ediciones')" type="button" class="btn mode" :disabled="!can('si_ediciones')" @click="choose('si_ediciones')">
              <Icon name="warn" :size="14" /> {{ CHOICE_LABEL.si_ediciones }}
            </button>
          </div>
          <p v-if="has('si_auto') || has('si_ediciones')" class="foot">Pide el PIN: la sesión deja de preguntarte por {{ has('si_auto') ? 'comandos' : 'ediciones' }}.</p>
          <p v-if="permiso.mas_en_terminal" class="foot">Hay más opciones en la terminal.</p>
        </template>

        <!-- question -->
        <template v-else-if="pregunta && cur">
          <div class="top">
            <span class="kicker mono">pregunta</span>
            <span v-if="many" class="tool mono">{{ summary ? 'Revisá' : `${step + 1} de ${qs.length}` }}</span>
            <span v-else-if="cur.header" class="tool mono">{{ cur.header }}</span>
            <span v-if="done" class="stamp mono"><Icon name="check" :size="12" /> Respondido</span>
          </div>
          <template v-if="summary">
            <h2 class="title">Tus respuestas</h2>
            <ul class="review">
              <li v-for="(q, i) in qs" :key="i">
                <button type="button" class="rev" :disabled="busy || done" @click="go(i)">
                  <span class="rq">{{ q.texto }}</span>
                  <span class="ra">{{ answerOf(i) }}</span>
                </button>
              </li>
            </ul>
          </template>
          <template v-else>
            <p v-if="many && cur.header" class="hdr mono">{{ cur.header }}</p>
            <h2 class="title">{{ cur.texto }}</h2>
            <p v-if="cur.multi" class="hint">Podés elegir más de una.</p>
            <div class="choices" :role="cur.multi ? 'group' : 'radiogroup'" :aria-label="cur.texto">
              <button
                v-for="(o, i) in cur.opciones"
                :key="`${step}-${i}`"
                type="button"
                class="choice"
                :class="{ multi: cur.multi }"
                :role="cur.multi ? 'checkbox' : 'radio'"
                :aria-checked="picksOf(step).includes(i)"
                :disabled="busy || done"
                @click="pick(i)"
              >
                <i class="dot" aria-hidden="true" />
                <span class="ctext"><span class="clabel">{{ o.label }}</span><span v-if="o.descripcion" class="cdesc">{{ o.descripcion }}</span></span>
              </button>
              <button v-if="cur.otro" type="button" class="choice" role="radio" :aria-checked="other" :disabled="busy || done" @click="pickOther">
                <i class="dot" aria-hidden="true" />
                <span class="ctext"><span class="clabel">Otra respuesta</span></span>
              </button>
            </div>
            <div v-if="other" class="otro">
              <textarea ref="input" v-model="text" rows="2" :maxlength="MAX_OTRO + 50" placeholder="Escribí tu respuesta" aria-label="Otra respuesta" :disabled="busy || done" @keydown.enter.prevent="sendPregunta" />
              <p class="count mono" :class="{ over: text.trim().length > MAX_OTRO }">{{ text.trim().length }}/{{ MAX_OTRO }}</p>
              <p v-if="problem" class="warn" role="alert"><Icon name="warn" :size="14" /> <span>{{ problem }}</span></p>
            </div>
          </template>
          <div class="actions">
            <button v-if="many && step > 0" type="button" class="btn ghost" :disabled="busy || done" @click="go(step - 1)">Volver</button>
            <button type="button" class="btn primary" :class="{ busy }" :disabled="!ready || busy || done || changed" :aria-busy="busy" @click="sendPregunta">
              <span v-if="busy" class="spin" aria-hidden="true" />{{ busy ? (dlg.phase === 'verifying' ? 'Verificando…' : 'Enviando…') : many && !summary ? (step === qs.length - 1 ? 'Revisar' : 'Siguiente') : 'Enviar respuesta' }}
            </button>
          </div>
          <p class="foot">{{ many || cur.multi ? 'Se manda todo junto al final.' : 'Hay más opciones en la terminal.' }}</p>
        </template>

        <!-- unknown -->
        <template v-else-if="view?.tipo === 'desconocido'">
          <div class="top"><span class="kicker mono">sin reconocer</span></div>
          <h2 class="title">Claude espera algo que no sé mostrarte</h2>
          <p class="desc">{{ vivo ? 'Abrí la terminal para verlo y responderlo. Desde acá no mando nada que no entienda.' : 'Respondelo en la terminal. Desde acá no mando nada que no entienda.' }}</p>
          <div class="actions">
            <button type="button" class="btn ghost" :aria-expanded="screenOpen" @click="screenOpen = !screenOpen">{{ screenOpen ? 'Ocultar pantalla' : 'Ver pantalla' }}</button>
            <button v-if="vivo" type="button" class="btn primary" @click="emit('vivo')"><Icon name="terminal" :size="14" /> Abrir terminal</button>
          </div>
          <pre v-if="screenOpen" class="code screen mono">{{ pantalla || '(vacía)' }}</pre>
        </template>

        <p v-if="changed" class="warn" data-kind="stale" role="alert"><Icon name="warn" :size="14" /> <span>El diálogo cambió</span></p>
        <p v-if="dlg.notice" class="warn" :data-kind="dlg.noticeKind" role="alert">
          <Icon name="warn" :size="14" /> <span>{{ dlg.notice }}</span>
        </p>
        <p v-if="dlg.loadError && !dlg.notice" class="warn" role="alert"><Icon name="warn" :size="14" /> <span>{{ dlg.loadError }}</span></p>
      </div>
    </section>
  </Transition>
</template>

<style scoped>
.dc {
  position: relative;
  margin: 14px 0 6px;
  padding: 14px 16px 16px;
  border-radius: var(--r-lg);
  background: var(--surface);
  border: 1px solid color-mix(in srgb, var(--st-blocked) 45%, transparent);
  box-shadow: 0 0 0 4px var(--st-blocked-soft), var(--shadow-pop);
  overflow: hidden;
  transition: border-color 0.4s, box-shadow 0.5s;
}
.edge {
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--st-blocked);
}
.dc[data-done='true'] {
  border-color: color-mix(in srgb, var(--st-done) 45%, transparent);
  box-shadow: 0 0 0 4px var(--st-done-soft);
}
.dc[data-done='true'] .edge {
  background: var(--st-done);
}
.stagger {
  display: grid;
  gap: 10px;
  min-width: 0;
}
.top {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.kicker {
  font-size: var(--t-xs);
  letter-spacing: 0.14em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--st-blocked);
}
.tool {
  font-size: 11px;
  padding: 2px 7px;
  border-radius: 6px;
  color: var(--text-3);
  background: var(--bg-2);
  border: 1px solid var(--line);
}
.stamp {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: var(--t-xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--st-done);
  padding: 3px 8px;
  border-radius: 6px;
  border: 1px solid color-mix(in srgb, var(--st-done) 45%, transparent);
}
.title {
  margin: 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  letter-spacing: -0.02em;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.desc {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
.file {
  margin: 0;
  font-size: 12px;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.code {
  margin: 0;
  padding: 10px 12px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  line-height: 1.55;
  color: var(--text);
  background: var(--bg-2);
  border: 1px solid var(--line);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  max-height: 16em;
  overflow: auto;
  overscroll-behavior: contain;
  min-width: 0;
}
.screen {
  max-height: 16em;
  overflow: auto;
  overscroll-behavior: contain;
}
.warn {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  padding: 9px 12px;
  border-radius: var(--r-md);
  font-size: 13px;
  line-height: 1.4;
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  border: 1px solid color-mix(in srgb, var(--st-blocked) 35%, transparent);
}
.warn[data-kind='half'],
.warn[data-kind='error'] {
  color: var(--danger);
  background: var(--danger-soft);
  border-color: color-mix(in srgb, var(--danger) 40%, transparent);
}
.warn span {
  min-width: 0;
  overflow-wrap: anywhere;
}
.warn svg {
  flex: none;
  margin-top: 2px;
}
.actions {
  display: grid;
  gap: 8px;
  margin-top: 2px;
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 46px;
  padding: 0 16px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 620;
  transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), box-shadow 0.25s, opacity 0.2s;
}
.btn:active:not(:disabled) {
  scale: var(--press-scale);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn.busy:disabled {
  opacity: 0.85;
}
.primary {
  background: var(--accent);
  color: var(--accent-ink);
}
.primary:hover:not(:disabled) {
  box-shadow: 0 0 0 4px var(--accent-soft, transparent), 0 8px 26px -10px var(--accent);
}
.ghost {
  color: var(--text-2);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.ghost:hover:not(:disabled) {
  color: var(--text);
  background: var(--surface-hover);
}
.always {
  height: 40px;
  font-size: var(--t-lg);
  color: var(--st-blocked);
  background: transparent;
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--st-blocked) 40%, transparent);
}
.always:hover:not(:disabled) {
  background: var(--st-blocked-soft);
}
.mode {
  height: 40px;
  font-size: var(--t-lg);
  color: var(--text-2);
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.mode svg {
  color: var(--st-blocked);
}
.mode:hover:not(:disabled) {
  background: var(--st-blocked-soft);
}
.rule,
.foot {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.rule b {
  color: var(--text-2);
  font-weight: 600;
}
.choices {
  display: grid;
  gap: 8px;
}
.choice {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  width: 100%;
  min-height: 48px;
  padding: 11px 14px;
  text-align: left;
  border-radius: 12px;
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, box-shadow 0.25s, scale 0.3s var(--spring);
}
.choice:active:not(:disabled) {
  scale: 0.985;
}
.choice[aria-checked='true'] {
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-2));
  box-shadow: inset 0 0 0 1.5px var(--accent);
}
.choice:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.dot {
  flex: none;
  width: 18px;
  height: 18px;
  margin-top: 1px;
  border-radius: 50%;
  box-shadow: inset 0 0 0 1.5px var(--text-4);
  transition: box-shadow 0.25s, background 0.25s;
}
.choice[aria-checked='true'] .dot {
  background: radial-gradient(circle, var(--accent) 0 4.5px, transparent 5.5px);
  box-shadow: inset 0 0 0 1.5px var(--accent);
}
.choice.multi .dot {
  border-radius: 6px;
}
.choice.multi[aria-checked='true'] .dot {
  background: var(--accent) radial-gradient(circle, transparent 0, transparent 0);
  box-shadow: inset 0 0 0 1.5px var(--accent), inset 0 0 0 5px var(--accent);
}
.hdr {
  font-size: 12px;
  color: var(--text-3);
}
.hint {
  font-size: 13px;
  color: var(--text-3);
}
.review {
  display: grid;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin: 0;
}
.rev {
  display: grid;
  gap: 2px;
  width: 100%;
  padding: 11px 14px;
  text-align: left;
  border-radius: 12px;
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.rq {
  font-size: 13px;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.ra {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  overflow-wrap: anywhere;
}
.ctext {
  display: grid;
  gap: 2px;
  min-width: 0;
}
.clabel {
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
  overflow-wrap: anywhere;
}
.cdesc {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.otro {
  display: grid;
  gap: 6px;
}
.otro textarea {
  width: 100%;
  resize: none;
  padding: 10px 12px;
  border-radius: 12px;
  font: inherit;
  font-size: 16px;
  line-height: 1.45;
  color: var(--text);
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  outline: none;
  transition: border-color 0.2s, box-shadow 0.25s;
}
.otro textarea:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}
.count {
  margin: 0;
  font-size: 11px;
  text-align: right;
  color: var(--text-4);
}
.count.over {
  color: var(--danger);
}
.spin {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1.5px solid currentColor;
  border-right-color: transparent;
  animation: spin 0.8s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
@media (min-width: 640px) {
  .actions {
    grid-auto-flow: column;
    grid-auto-columns: max-content;
    align-items: center;
  }
  .btn {
    height: 40px;
  }
}
:root[data-motion='soft'] .spin {
  animation-duration: 1.6s;
}
</style>
