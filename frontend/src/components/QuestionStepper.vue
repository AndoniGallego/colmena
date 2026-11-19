<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Opciones } from '../lib/opciones'
import {
  advance,
  allAnswered,
  answer,
  answerLine,
  back,
  buildReply,
  canNext,
  goTo,
  isAnswered,
  isSummary,
  next,
  stepperKey,
  type StepperState,
} from '../lib/stepper'
import { autosizeArea } from '../lib/autosize'
import { finePointer, gsap, haptic, isSoft, ring, useGsap } from '../motion'
import Icon from './Icon.vue'

const props = defineProps<{
  questions: Opciones[]
  modelValue: StepperState
  /** keys are read from the whole window only when this is the stepper in front */
  keys?: boolean
  sending?: boolean
  /** one gray line about where the question comes from */
  contexto?: string
  dismissLabel?: string
}>()
const emit = defineEmits<{ 'update:modelValue': [s: StepperState]; send: [text: string]; dismiss: []; minimize: [] }>()

const n = computed(() => props.questions.length)
const st = computed(() => props.modelValue)
const summary = computed(() => isSummary(n.value, st.value))
const q = computed(() => (summary.value ? null : props.questions[st.value.step]))
const cur = computed(() => st.value.answers[st.value.step] ?? null)
const freeOnly = computed(() => !!q.value && !q.value.opciones.length)
const chosen = computed(() => (cur.value?.kind === 'opcion' ? cur.value.i : -1))
const reply = computed(() => buildReply(props.questions, st.value.answers))
const answeredCount = computed(() => props.questions.filter((qq, k) => isAnswered(qq, st.value.answers[k])).length)
const kicker = computed(() => {
  if (summary.value) return 'Revisá y enviá'
  return n.value === 1 ? 'Una pregunta para vos' : `Pregunta ${st.value.step + 1} de ${n.value}`
})
const desk = ref(finePointer())

const root = ref<HTMLElement | null>(null)
const viewport = ref<HTMLElement | null>(null)
const area = ref<HTMLTextAreaElement | null>(null)
const writing = ref(false)
const draft = ref('')
const dir = ref(1)
let advanceTimer: ReturnType<typeof setTimeout> | undefined

const { run } = useGsap()

function set(s: StepperState) {
  if (s === st.value) return
  dir.value = s.step >= st.value.step ? 1 : -1
  emit('update:modelValue', s)
}

watch(
  () => st.value.step,
  () => {
    clearTimeout(advanceTimer)
    const a = st.value.answers[st.value.step]
    writing.value = a?.kind === 'texto' || freeOnly.value
    draft.value = a?.kind === 'texto' ? a.text : ''
    if (freeOnly.value && desk.value && root.value?.contains(document.activeElement)) nextTick(() => area.value?.focus())
  },
  { immediate: true },
)

function bump(el: Element | null) {
  if (!el || isSoft()) return
  run(() => gsap.fromTo(el, { scale: 0.97 }, { scale: 1, duration: 0.3, ease: 'power3.out' }))
}

function pick(i: number, el?: Element | null) {
  const qq = q.value
  if (!qq || props.sending || !qq.opciones[i]) return
  haptic(10)
  const btn = el ?? root.value?.querySelector(`[data-opt="${i}"]`) ?? null
  if (btn && !isSoft()) {
    const accent = getComputedStyle(btn).getPropertyValue('--accent')
    ring(btn.querySelector('.n') ?? btn, accent, 58)
    bump(btn)
  }
  writing.value = false
  const s = answer(props.questions, st.value, { kind: 'opcion', i })
  if (n.value === 1) {
    emit('update:modelValue', s)
    emit('send', answerLine(qq, s.answers[0]))
    return
  }
  emit('update:modelValue', s)
  clearTimeout(advanceTimer)
  const from = s.step
  advanceTimer = setTimeout(() => {
    if (st.value.step === from) set(advance(props.questions, st.value))
  }, isSoft() ? 120 : 300)
}

async function openWriting() {
  if (props.sending) return
  haptic(6)
  writing.value = true
  await nextTick()
  const el = area.value
  if (!el) return
  el.focus()
  fit()
  if (!isSoft()) run(() => gsap.from(el.parentElement, { y: 8, opacity: 0, scale: 0.98, duration: 0.3, ease: 'power3.out' }))
}

function fit() {
  if (area.value) autosizeArea(area.value, 140)
}

function useDraft() {
  const text = draft.value.trim()
  const qq = q.value
  if (!qq || !text || props.sending) return
  haptic(8)
  const s = answer(props.questions, st.value, { kind: 'texto', text })
  if (n.value === 1) {
    emit('update:modelValue', s)
    emit('send', answerLine(qq, s.answers[0]))
    return
  }
  set(advance(props.questions, s))
}

function cancelWriting() {
  if (freeOnly.value) return dismiss()
  writing.value = false
  draft.value = cur.value?.kind === 'texto' ? cur.value.text : ''
  root.value?.focus()
}

function goNext() {
  if (summary.value) return submit()
  if (writing.value && draft.value.trim()) return useDraft()
  if (!canNext(props.questions, st.value)) return
  clearTimeout(advanceTimer)
  set(allAnswered(props.questions, st.value) ? goTo(props.questions, st.value, n.value) : next(props.questions, st.value))
}

function goBack() {
  if (st.value.step === 0) return
  clearTimeout(advanceTimer)
  set(back(st.value))
}

function jump(k: number) {
  clearTimeout(advanceTimer)
  set(goTo(props.questions, st.value, k))
}

const sendBtn = ref<HTMLElement | null>(null)
function submit() {
  const text = reply.value
  if (!text || props.sending) return
  haptic([10, 30, 16])
  if (sendBtn.value && !isSoft()) ring(sendBtn.value, getComputedStyle(sendBtn.value).getPropertyValue('--accent'), 80)
  emit('send', text)
}

function dismiss() {
  clearTimeout(advanceTimer)
  emit('dismiss')
}

function minimize() {
  clearTimeout(advanceTimer)
  emit('minimize')
}

function onKey(e: KeyboardEvent) {
  const typing = (e.target as HTMLElement | null)?.tagName === 'TEXTAREA'
  const k = stepperKey(e, typing)
  if (!k) return
  if (k.type === 'escape') {
    e.preventDefault()
    if (typing && writing.value) cancelWriting()
    else dismiss()
    return
  }
  if (k.type === 'minimize') {
    e.preventDefault()
    minimize()
    return
  }
  if (k.type === 'pick') {
    if (summary.value) {
      if (k.i < n.value) jump(k.i)
    } else if (q.value?.opciones[k.i]) pick(k.i)
    else return
  } else if (k.type === 'enter') goNext()
  else if (k.type === 'back') goBack()
  else if (k.type === 'forward') goNext()
  e.preventDefault()
}

// Keys typed with nothing focused reach the stepper in front, so the numbers work right after it opens.
function onWindowKey(e: KeyboardEvent) {
  if (!props.keys || e.defaultPrevented) return
  const a = document.activeElement
  if (a && a !== document.body) return
  onKey(e)
}
onMounted(() => window.addEventListener('keydown', onWindowKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onWindowKey)
  clearTimeout(advanceTimer)
})

// ---------- slide between steps, the card height follows ----------
let fromH = 0
function onBeforeLeave() {
  const v = viewport.value
  if (!v) return
  fromH = v.offsetHeight
  v.style.height = `${fromH}px`
}
function onLeave(el: Element, done: () => void) {
  if (isSoft()) {
    gsap.to(el, { opacity: 0, duration: 0.12, onComplete: done })
    return
  }
  gsap.to(el, { x: -dir.value * 42, opacity: 0, duration: 0.17, ease: 'power2.in', onComplete: done })
}
function onEnter(el: Element, done: () => void) {
  const v = viewport.value
  const target = v ? (v.style.height = 'auto', v.offsetHeight) : 0
  if (v) v.style.height = `${fromH || target}px`
  if (isSoft()) {
    if (v) v.style.height = ''
    gsap.from(el, { opacity: 0, duration: 0.18, onComplete: done })
    return
  }
  if (v) gsap.to(v, { height: target, duration: 0.5, ease: 'orq.spring', clearProps: 'height' })
  const sel = gsap.utils.selector(el)
  gsap
    .timeline({ onComplete: done })
    .fromTo(el, { x: dir.value * 56, opacity: 0 }, { x: 0, opacity: 1, duration: 0.3, ease: 'power3.out', clearProps: 'transform' })
    .from(sel('.opt, .row'), { y: 12, opacity: 0, scale: 0.97, duration: 0.3, ease: 'power3.out', stagger: 0.045, clearProps: 'transform,opacity' }, 0.06)
}

defineExpose({
  focus: () => (freeOnly.value && desk.value && area.value ? area.value.focus({ preventScroll: true }) : root.value?.focus({ preventScroll: true })),
  el: root,
})
</script>

<template>
  <section ref="root" class="stp" :class="{ one: n === 1, desk }" tabindex="-1" aria-label="Preguntas pendientes" @keydown="onKey">
    <slot name="fuente" />
    <header class="top">
      <span class="badge" aria-hidden="true"><Icon name="ask" :size="13" /></span>
      <p class="kicker" aria-live="polite">{{ kicker }}</p>
      <button type="button" class="esc" @click="dismiss">
        <Icon :name="dismissLabel ? 'clock' : 'pen'" :size="12" /><span>{{ dismissLabel || 'Escribir otra cosa' }}</span><kbd v-if="desk" class="mono">Esc</kbd>
      </button>
      <button type="button" class="mini hit" aria-label="Minimizar preguntas" title="Minimizar (M)" @click="minimize">
        <Icon class="dn" name="chevron" :size="16" />
      </button>
    </header>

    <div v-if="n > 1" class="prog" role="group" aria-label="Progreso">
      <button
        v-for="(qq, k) in questions"
        :key="k"
        type="button"
        class="seg hit"
        :class="{ on: st.step === k, done: isAnswered(qq, st.answers[k]) }"
        :aria-label="`Pregunta ${k + 1}${isAnswered(qq, st.answers[k]) ? ', respondida' : ''}`"
        :aria-current="st.step === k ? 'step' : undefined"
        @click="jump(k)"
      ><i /></button>
      <button
        type="button"
        class="seg end hit"
        :class="{ on: summary, done: answeredCount === n }"
        :aria-label="answeredCount === n ? 'Resumen' : 'Resumen, falta responder'"
        :aria-current="summary ? 'step' : undefined"
        @click="jump(n)"
      ><Icon name="check" :size="10" /></button>
    </div>

    <div ref="viewport" class="viewport">
      <Transition :css="false" mode="out-in" @before-leave="onBeforeLeave" @leave="onLeave" @enter="onEnter">
        <div v-if="q" :key="`q${st.step}`" class="pane">
          <p class="q">{{ q.pregunta || 'Elegí una opción' }}</p>
          <p v-if="contexto" class="ctx">{{ contexto }}</p>
          <div v-if="q.opciones.length" class="list" role="group" :aria-label="q.pregunta || 'Opciones'">
            <button
              v-for="(o, i) in q.opciones"
              :key="i"
              type="button"
              class="opt hit"
              :data-opt="i"
              :class="{ rec: o.recomendada, chosen: chosen === i, dim: chosen >= 0 && chosen !== i }"
              :aria-pressed="chosen === i"
              :disabled="sending"
              @click="pick(i, $event.currentTarget as Element)"
            >
              <span class="n mono" aria-hidden="true"><Icon v-if="chosen === i" name="check" :size="14" /><template v-else>{{ i + 1 }}</template></span>
              <span class="txt">
                <span class="label">{{ o.label }}<span v-if="o.recomendada" class="rec-chip">Recomendada</span></span>
                <span v-if="o.detalle" class="detalle">{{ o.detalle }}</span>
              </span>
            </button>
          </div>
          <div v-if="writing" class="free" :class="{ chosen: cur?.kind === 'texto' }">
            <textarea
              ref="area"
              v-model="draft"
              rows="1"
              placeholder="Escribí tu respuesta…"
              :aria-label="freeOnly ? 'Tu respuesta' : 'Otra respuesta'"
              :enterkeyhint="n === 1 || answeredCount >= n - 1 ? 'send' : 'next'"
              @input="fit"
            />
            <button type="button" class="use hit" :disabled="!draft.trim() || sending" :aria-label="n === 1 ? 'Enviar respuesta' : 'Usar esta respuesta'" @click="useDraft">
              <Icon :name="n === 1 ? 'arrow-up' : 'arrow-right'" :size="15" />
            </button>
          </div>
          <button v-else type="button" class="other" :disabled="sending" @click="openWriting"><Icon name="pen" :size="12" /> Otra respuesta…</button>
        </div>

        <div v-else key="sum" class="pane sum">
          <p class="q">¿Va así?</p>
          <ol class="rows">
            <li v-for="(qq, k) in questions" :key="k">
              <button type="button" class="row" :aria-label="`Cambiar respuesta ${k + 1}`" @click="jump(k)">
                <span class="n mono" aria-hidden="true">{{ k + 1 }}</span>
                <span class="txt">
                  <span class="rq">{{ qq.pregunta || `Pregunta ${k + 1}` }}</span>
                  <span class="ra">{{ st.answers[k]?.kind === 'texto' ? answerLine(qq, st.answers[k]) : qq.opciones[(st.answers[k] as { i: number } | null)?.i ?? -1]?.label }}</span>
                </span>
                <span class="edit" aria-hidden="true"><Icon name="pen" :size="12" /></span>
              </button>
            </li>
          </ol>
        </div>
      </Transition>
    </div>

    <footer v-if="n > 1" class="nav">
      <button type="button" class="ghost" :disabled="st.step === 0 || sending" @click="goBack"><Icon name="back" :size="14" /><span>Atrás</span></button>
      <span v-if="desk" class="hint mono">{{ summary ? 'Enter envía · M minimiza' : freeOnly ? 'Enter sigue' : '1–' + (q?.opciones.length ?? 6) + ' elige · Enter sigue · M minimiza' }}</span>
      <button
        v-if="summary"
        ref="sendBtn"
        type="button"
        class="go"
        :disabled="!reply || sending"
        @click="submit"
      ><Icon name="arrow-up" :size="15" /><span>{{ sending ? 'Enviando…' : 'Enviar' }}</span></button>
      <button v-else type="button" class="go soft" :disabled="!(canNext(questions, st) || (writing && draft.trim())) || sending" @click="goNext">
        <span>Siguiente</span><Icon name="arrow-right" :size="14" />
      </button>
    </footer>
    <p v-else-if="desk" class="hint solo mono">{{ freeOnly ? 'Enter envía · Shift+Enter salto de línea' : `1–${q?.opciones.length ?? 6} responde · Esc ${dismissLabel ? 'para después' : 'para escribir otra cosa'} · M minimiza` }}</p>
  </section>
</template>

<style scoped>
.stp {
  position: relative;
  display: grid;
  gap: 10px;
  padding: 12px 12px 10px;
  border-radius: 20px;
  background:
    radial-gradient(120% 70% at 50% 0%, var(--accent-soft), transparent 72%),
    var(--surface);
  border: 1px solid var(--accent-line);
  box-shadow: var(--shadow-pop), 0 18px 50px -28px var(--accent);
  outline: none;
  transform-origin: 50% 100%;
}
.stp:focus-visible {
  box-shadow: var(--shadow-pop), 0 0 0 3px var(--accent-soft);
}
.top {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.badge {
  flex: none;
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 8px;
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: 0 0 16px -4px var(--accent);
}
.kicker {
  flex: 1;
  min-width: 0;
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mini {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  margin: -2px -4px -2px 0;
  border-radius: 12px;
  color: var(--text-2, var(--text-3));
  background: color-mix(in srgb, var(--surface-2) 80%, transparent);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: color 0.2s, background 0.2s, scale 0.35s var(--spring);
}
.mini:hover {
  color: var(--text);
  background: var(--surface-hover);
}
.mini:active {
  scale: var(--press-scale);
}
.mini .dn { rotate: 90deg; }
.esc {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 36px;
  padding: 0 10px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  color: var(--text-3);
  transition: color 0.2s, background 0.2s, scale 0.35s var(--spring);
}
.esc:hover {
  color: var(--text);
  background: var(--surface-hover);
}
.esc:active {
  scale: var(--press-scale);
}
kbd {
  padding: 1px 5px;
  border-radius: 5px;
  font-size: var(--t-xs);
  color: var(--text-4);
  box-shadow: inset 0 0 0 1px var(--line-2);
}

.prog {
  display: flex;
  align-items: center;
  gap: 4px;
  margin: -2px 2px 0;
}
.seg {
  flex: 1;
  display: grid;
  align-items: center;
  height: 18px;
  padding: 0;
  cursor: pointer;
}
.seg i {
  display: block;
  height: 4px;
  border-radius: 99px;
  background: var(--line-2);
  position: relative;
  overflow: hidden;
  transition: height 0.3s var(--spring), background 0.3s;
}
.seg i::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: var(--accent);
  transform: scaleX(0);
  transform-origin: left;
  transition: transform 0.55s var(--spring);
}
.seg.done i::after {
  transform: scaleX(1);
}
.seg.on i {
  height: 6px;
  background: color-mix(in srgb, var(--accent) 30%, var(--line-2));
}
.seg.on:not(.done) i::after {
  transform: scaleX(0.18);
}
.seg.end {
  flex: none;
  width: 18px;
  height: 18px;
  place-items: center;
  border-radius: 6px;
  color: var(--text-4);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: color 0.3s, background 0.3s, box-shadow 0.3s, scale 0.35s var(--spring);
}
.seg.end.done {
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.seg.end.on {
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: none;
  scale: 1.08;
}

.viewport {
  position: relative;
  max-height: min(58vh, 520px);
  max-height: min(58dvh, 520px);
  overflow-x: hidden;
  overflow-y: auto;
  overscroll-behavior: contain;
  margin: 0 -4px;
  padding: 0 4px;
}
.kb-open .viewport {
  max-height: 34dvh;
}
.pane {
  padding: 2px 0 4px;
}
.q {
  margin: 0 4px 12px;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  line-height: 1.28;
  letter-spacing: -0.015em;
  color: var(--text);
  overflow-wrap: anywhere;
  text-wrap: pretty;
}
.ctx {
  margin: -6px 4px 12px;
  font-size: var(--t-md);
  line-height: 1.4;
  color: var(--text-3);
  overflow-wrap: anywhere;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.list {
  display: grid;
  gap: 8px;
}
.opt {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 56px;
  padding: 10px 14px 10px 10px;
  border-radius: var(--r-lg);
  text-align: left;
  color: var(--text);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.25s, box-shadow 0.3s, translate 0.35s var(--spring), scale 0.35s var(--spring);
  -webkit-tap-highlight-color: transparent;
}
.opt.rec {
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
@media (hover: hover) {
  .opt:not(:disabled):hover {
    translate: 0 -1px;
    background: var(--surface-hover);
    box-shadow: inset 0 0 0 1px var(--accent-line), 0 8px 22px -12px var(--accent);
  }
  .opt:not(:disabled):hover .n {
    scale: 1.06;
  }
}
.opt:not(:disabled):active {
  scale: 0.975;
}
.n {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
  transition: background 0.3s, color 0.3s, scale 0.35s var(--spring), opacity 0.35s;
}
.rec .n,
.opt.chosen .n {
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: none;
}
.txt {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
  transition: opacity 0.35s;
}
.label {
  font-size: 15px;
  font-weight: 580;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.rec-chip {
  display: inline-block;
  margin-left: 8px;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  vertical-align: 1px;
  font-size: var(--t-xs);
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
  white-space: nowrap;
}
.detalle {
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.opt.chosen {
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1.5px var(--accent), 0 0 24px -8px var(--accent);
}
.opt.dim .txt,
.opt.dim .n {
  opacity: 0.5;
}
.other {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  min-height: 44px;
  margin-top: 6px;
  border-radius: 12px;
  font-size: 13px;
  color: var(--text-3);
  box-shadow: inset 0 0 0 1px transparent;
  transition: color 0.2s, box-shadow 0.25s, background 0.2s;
}
.other:hover:not(:disabled) {
  color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.free {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin-top: 8px;
  padding: 5px 5px 5px 12px;
  border-radius: var(--r-lg);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--accent-line);
  transition: box-shadow 0.3s;
}
.free:focus-within {
  box-shadow: inset 0 0 0 1.5px var(--accent), 0 0 0 3px var(--accent-soft);
}
.free textarea {
  flex: 1;
  min-width: 0;
  resize: none;
  border: 0;
  outline: none !important;
  background: none;
  color: var(--text);
  font: inherit;
  font-size: 16px;
  line-height: 1.45;
  padding: 7px 0;
  min-height: 38px;
}
.free textarea::placeholder {
  color: var(--text-4);
}
.use {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: var(--r-md);
  color: var(--accent-ink);
  background: var(--accent);
  transition: opacity 0.2s, scale 0.35s var(--spring), background 0.2s;
}
.use:disabled {
  color: var(--text-4);
  background: var(--surface-hover);
  cursor: default;
}
.use:not(:disabled):active {
  scale: var(--press-scale);
}

.rows {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 54px;
  padding: 9px 12px 9px 10px;
  border-radius: var(--r-lg);
  text-align: left;
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.25s, box-shadow 0.3s, scale 0.35s var(--spring);
}
.row .n {
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: none;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  font-size: 12px;
}
.row:active {
  scale: 0.98;
}
.rq {
  font-size: 12px;
  line-height: 1.35;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ra {
  font-size: 14.5px;
  font-weight: 580;
  line-height: 1.3;
  color: var(--text);
  overflow-wrap: anywhere;
}
.edit {
  flex: none;
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  border-radius: var(--r-md);
  color: var(--text-4);
  transition: color 0.2s, background 0.2s;
}
@media (hover: hover) {
  .row:hover {
    background: var(--surface-hover);
    box-shadow: inset 0 0 0 1px var(--accent-line);
  }
  .row:hover .edit {
    color: var(--accent);
    background: var(--accent-soft);
  }
}

.nav {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-top: 2px;
}
.hint {
  flex: 1;
  min-width: 0;
  text-align: center;
  font-size: 11px;
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hint.solo {
  margin: -2px 0 0;
}
.ghost {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 44px;
  padding: 0 14px 0 10px;
  border-radius: 12px;
  font-size: var(--t-lg);
  color: var(--text-2);
  transition: color 0.2s, background 0.2s, opacity 0.2s, scale 0.35s var(--spring);
}
.ghost:hover:not(:disabled) {
  color: var(--text);
  background: var(--surface-hover);
}
.ghost:disabled {
  opacity: 0.35;
  cursor: default;
}
.ghost:not(:disabled):active {
  scale: var(--press-scale);
}
.go {
  margin-left: auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  min-height: 44px;
  min-width: 128px;
  padding: 0 20px;
  border-radius: var(--r-pill);
  font-size: 14px;
  font-weight: 600;
  white-space: nowrap;
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: 0 10px 26px -12px var(--accent);
  transition: opacity 0.3s, background 0.3s, color 0.3s, box-shadow 0.3s, scale 0.35s var(--spring);
}
.go.soft {
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.go:disabled {
  cursor: default;
  color: var(--text-4);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.go:not(:disabled):active {
  scale: var(--press-scale);
}
@media (max-width: 1023px) {
  .stp {
    padding: 11px 10px 8px;
    border-radius: 18px;
  }
  .q {
    font-size: 17px;
  }
  .go {
    flex: 1;
  }
}
@media (max-width: 480px) {
  .rec-chip {
    display: table;
    margin: 3px 0 1px;
  }
}
</style>
