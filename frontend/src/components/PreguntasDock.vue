<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, shallowRef, watch } from 'vue'
import { clearProgreso, initial, loadProgreso, minLabel, restore, saveProgreso, type StepperState } from '../lib/stepper'
import { chipLabel, type LoteDock } from '../lib/dock'
import { desktop } from '../lib/viewport'
import { finePointer, gsap, haptic, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import QuestionStepper from './QuestionStepper.vue'

const props = defineProps<{
  /** questions still waiting for the user here, in the order they are offered */
  lotes: LoteDock[]
  /** changes when the dock moves to another chat: the swap skips the morph */
  chatKey: string
  /** waiting for an approval: the input stays; a working session does not hold it */
  hold?: boolean
  /** this chat is on screen, so its stepper takes the keys */
  active?: boolean
  send: (lote: LoteDock, text: string) => unknown
}>()

interface Slot {
  sig: string
  state: StepperState
  dismissed: boolean
  minimizado: boolean
}
const slots = reactive<Record<string, Slot>>({})

const host = ref<HTMLElement | null>(null)
const slot = ref<HTMLElement | null>(null)
const card = ref<InstanceType<typeof QuestionStepper> | null>(null)
const cardEl = () => card.value?.el ?? null

function ensure(l: LoteDock) {
  const cur = slots[l.key]
  if (cur && cur.sig === l.sig) return
  const saved = loadProgreso(l.key)
  const r = restore(l.questions, l.sig, saved)
  slots[l.key] = { sig: l.sig, state: r.state, dismissed: r.dismissed, minimizado: r.minimizado }
}

const curKey = ref<string | null>(null)
const sendingId = ref<string | null>(null)
const idOf = (l: LoteDock) => `${l.key}\u0001${l.sig}`

function sync() {
  const keys = new Set(props.lotes.map((l) => l.key))
  for (const k of Object.keys(slots)) if (!keys.has(k)) delete slots[k]
  props.lotes.forEach(ensure)
  if (sendingId.value && !props.lotes.some((l) => idOf(l) === sendingId.value)) sendingId.value = null
}
sync()
// Another chat or another set of questions: start from what was saved, before anything reacts to it.
watch(() => [props.chatKey, props.lotes.map(idOf).join('|')] as const, sync, { flush: 'sync' })

watch(
  () => Object.entries(slots).map(([k, v]) => [k, v.sig, v.state, v.dismissed, v.minimizado]),
  () => {
    for (const [k, v] of Object.entries(slots)) saveProgreso(k, { sig: v.sig, step: v.state.step, answers: v.state.answers, dismissed: v.dismissed, minimizado: v.minimizado })
  },
  { deep: true },
)

const abiertos = computed(() => props.lotes.filter((l) => slots[l.key] && !slots[l.key].dismissed))
const lote = computed(() => abiertos.value.find((l) => l.key === curKey.value) ?? abiertos.value[0] ?? null)
// What the card shows; it outlives the batch so the card can shrink away after sending.
const shown = shallowRef<LoteDock | null>(lote.value)
watch(lote, (l) => l && (shown.value = l))

let lastState: StepperState = initial(0)
const state = computed<StepperState>({
  get: () => {
    const s = shown.value && slots[shown.value.key]
    if (s && s.sig === shown.value!.sig) lastState = s.state
    return lastState
  },
  set: (v) => {
    const s = shown.value && slots[shown.value.key]
    if (s) s.state = v
  },
})
const sending = computed(() => !!shown.value && sendingId.value === idOf(shown.value))

const n = computed(() => props.lotes.length)
const wanted = computed(() => !!lote.value && !props.hold)
const chip = computed(() => !!n.value && !props.hold && !lote.value)
// Minimized on purpose: a thin bar with the progress instead of the "Responder" chip; the input stays usable.
const minLote = computed(() => (chip.value ? props.lotes.find((l) => slots[l.key]?.minimizado) ?? null : null))
const minText = computed(() => {
  const l = minLote.value
  const s = l && slots[l.key]
  if (!l || !s) return ''
  const base = minLabel(l.questions, s.state)
  return props.lotes.length > 1 ? `${base} · ${props.lotes.length} grupos` : base
})
const mode = ref<'input' | 'card'>(wanted.value ? 'card' : 'input')

const { run } = useGsap()
let token = 0

const tween = (target: gsap.TweenTarget, vars: gsap.TweenVars) =>
  new Promise<void>((done) => run(() => gsap.to(target, { ...vars, onComplete: done })))

function settle() {
  const els = [host.value, slot.value, cardEl()].filter(Boolean) as HTMLElement[]
  gsap.killTweensOf(els)
  gsap.set(els, { clearProps: 'height,transform,opacity,filter' })
}

function focusInput() {
  slot.value?.querySelector<HTMLTextAreaElement>('textarea')?.focus()
}

async function toCard(animate: boolean) {
  const my = ++token
  if (!animate || isSoft() || !host.value || !slot.value) {
    settle()
    mode.value = 'card'
    await nextTick()
    if (my !== token) return
    const el = cardEl()
    if (el && animate) run(() => gsap.from(el, { opacity: 0, duration: 0.22 }))
    if (finePointer() && props.active) card.value?.focus()
    return
  }
  const h0 = host.value.offsetHeight
  const w0 = slot.value.offsetWidth
  gsap.set(host.value, { height: h0 })
  // The input folds into its middle: narrower, flatter, gone.
  await tween(slot.value, { scaleX: 0.72, scaleY: 0.18, opacity: 0, duration: 0.3, ease: 'power3.in', transformOrigin: '50% 55%' })
  if (my !== token) return
  mode.value = 'card'
  await nextTick()
  if (my !== token) return
  gsap.set(slot.value, { clearProps: 'transform,opacity' })
  const el = cardEl()
  if (!el || !host.value) return settle()
  const h1 = el.offsetHeight
  const w1 = el.offsetWidth || w0
  const q = gsap.utils.selector(el)
  run(() => {
    gsap.to(host.value, { height: h1, duration: 0.62, ease: 'orq.spring', clearProps: 'height' })
    gsap
      .timeline()
      .fromTo(
        el,
        { scaleX: (w0 * 0.72) / w1, scaleY: Math.min(1, (h0 * 0.3) / h1), opacity: 0, transformOrigin: '50% 100%' },
        { scaleX: 1, scaleY: 1, opacity: 1, duration: 0.7, ease: 'orq.spring', clearProps: 'transform,opacity' },
      )
      .from(q('.top > *'), { y: 8, opacity: 0, duration: 0.4, ease: 'power3.out', stagger: 0.04, clearProps: 'transform,opacity' }, 0.12)
      .from(q('.prog .seg'), { scaleX: 0, opacity: 0, transformOrigin: '0% 50%', duration: 0.45, ease: 'orq.pop', stagger: 0.04, clearProps: 'transform,opacity' }, 0.16)
      .from(q('.pane .q'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', clearProps: 'transform,opacity' }, 0.18)
      .from(q('.pane .opt, .pane .row'), { y: 16, opacity: 0, scale: 0.96, duration: 0.3, ease: 'power3.out', stagger: 0.06, clearProps: 'transform,opacity' }, 0.22)
      .from(q('.other, .nav, .hint'), { opacity: 0, duration: 0.35, clearProps: 'opacity' }, 0.42)
  })
  haptic(8)
  if (finePointer() && props.active) card.value?.focus()
}

async function toInput(animate: boolean, focus = false) {
  const my = ++token
  const el = cardEl()
  if (!animate || isSoft() || !host.value || !el || !slot.value) {
    settle()
    mode.value = 'input'
    await nextTick()
    if (my !== token) return
    if (slot.value && animate) run(() => gsap.from(slot.value, { opacity: 0, duration: 0.22 }))
    if (focus) focusInput()
    return
  }
  const h1 = host.value.offsetHeight
  gsap.set(host.value, { height: h1 })
  await tween(el, { scaleX: 0.8, scaleY: 0.22, y: 8, opacity: 0, duration: 0.32, ease: 'power3.in', transformOrigin: '50% 100%' })
  if (my !== token) return
  mode.value = 'input'
  await nextTick()
  if (my !== token || !host.value || !slot.value) return
  const h0 = slot.value.offsetHeight
  run(() => {
    gsap.to(host.value, { height: h0, duration: 0.55, ease: 'orq.spring', clearProps: 'height' })
    gsap.fromTo(
      slot.value,
      { scaleX: 0.72, scaleY: 0.3, opacity: 0, transformOrigin: '50% 55%' },
      { scaleX: 1, scaleY: 1, opacity: 1, duration: 0.68, ease: 'orq.spring', clearProps: 'transform,opacity' },
    )
  })
  if (focus) focusInput()
}

let focusAfter = false
watch(
  () => [wanted.value, props.chatKey] as const,
  ([w, key], [, oldKey]) => {
    const f = focusAfter
    focusAfter = false
    if (w === (mode.value === 'card')) return
    // Switching chats swaps without the morph; the morph is for this chat's own changes.
    const animate = key === oldKey
    void (w ? toCard(animate) : toInput(animate, f))
  },
)

// ---------- moving between batches ----------
const swapDir = 1
watch(
  () => shown.value?.key,
  async (k, old) => {
    if (!k || !old || k === old || mode.value !== 'card' || !host.value) return
    const h0 = host.value.offsetHeight
    await nextTick()
    const el = cardEl()
    if (!el || !host.value) return
    if (finePointer() && props.active) card.value?.focus()
    if (isSoft()) return void run(() => gsap.from(el, { opacity: 0, duration: 0.18 }))
    const h1 = el.offsetHeight
    const q = gsap.utils.selector(el)
    run(() => {
      gsap.fromTo(host.value, { height: h0 }, { height: h1, duration: 0.5, ease: 'orq.spring', clearProps: 'height' })
      gsap
        .timeline()
        .fromTo(el, { x: swapDir * 46, opacity: 0 }, { x: 0, opacity: 1, duration: 0.3, ease: 'power3.out', clearProps: 'transform,opacity' })
        .from(q('.pane .opt, .pane .free'), { y: 12, opacity: 0, scale: 0.97, duration: 0.3, ease: 'power3.out', stagger: 0.045, clearProps: 'transform,opacity' }, 0.08)
    })
  },
  { flush: 'pre' },
)

function onWindowKey(e: KeyboardEvent) {
  // With the bar on screen and nothing focused, M opens it again.
  if (props.active && minLote.value && mode.value === 'input' && (e.key === 'm' || e.key === 'M') && !e.altKey && !e.ctrlKey && !e.metaKey && !e.isComposing) {
    const a = document.activeElement
    if (!a || a === document.body) {
      e.preventDefault()
      return reopen()
    }
  }
}

// ---------- open, put away, reopen ----------
function dismiss(focus = true) {
  if (!n.value) return
  haptic(6)
  focusAfter = focus
  for (const l of props.lotes) if (slots[l.key]) Object.assign(slots[l.key], { dismissed: true, minimizado: false })
}

// Put away to keep reading the chat: answers and step stay; the input is left as it was, no focus (no keyboard pops up).
function minimize() {
  if (!n.value) return
  haptic(6)
  focusAfter = false
  for (const l of props.lotes) if (slots[l.key]) Object.assign(slots[l.key], { dismissed: true, minimizado: true })
}

function reopen() {
  haptic(10)
  for (const l of props.lotes) if (slots[l.key]) Object.assign(slots[l.key], { dismissed: false, minimizado: false })
  curKey.value = props.lotes[0]?.key ?? null
}

async function onSend(text: string) {
  const l = shown.value
  if (!l || sending.value || !text.trim()) return
  const id = idOf(l)
  sendingId.value = id
  let ok: unknown = true
  try {
    ok = await props.send(l, text)
  } catch {
    ok = false
  }
  if (ok === false) {
    if (sendingId.value === id) sendingId.value = null
    return
  }
  clearProgreso(l.key)
  if (props.lotes.some((x) => idOf(x) === id)) {
    if (slots[l.key]) slots[l.key].state = initial(l.questions.length)
    if (sendingId.value === id) sendingId.value = null
  }
}

onMounted(() => {
  window.addEventListener('keydown', onWindowKey)
  if (mode.value === 'card' && finePointer() && props.active) nextTick(() => card.value?.focus())
})
onBeforeUnmount(() => window.removeEventListener('keydown', onWindowKey))

/** Gives the input back (for "Otra respuesta…" inside a message card). */
defineExpose({
  release: () => {
    if (mode.value !== 'card') return false
    dismiss(true)
    return true
  },
})
</script>

<template>
  <div ref="host" class="pdock" :class="{ open: mode === 'card' }">
    <Transition name="chip">
      <button
        v-if="minLote && mode === 'input'"
        key="min"
        type="button"
        class="pmin"
        :aria-label="`Expandir preguntas. ${minText}`"
        aria-expanded="false"
        :title="desktop ? 'Expandir (M)' : undefined"
        @click="reopen"
      >
        <span class="dot" aria-hidden="true" />
        <span class="ptxt">{{ minText }}</span>
        <Icon class="up" name="chevron" :size="16" />
      </button>
      <button v-else-if="chip && mode === 'input'" key="chip" type="button" class="pchip" @click="reopen">
        <span class="dot" aria-hidden="true" />
        <span class="ptxt">{{ chipLabel(lotes) }}</span>
        <span class="pgo">Responder <Icon name="arrow-up" :size="12" /></span>
      </button>
    </Transition>
    <div ref="slot" v-show="mode === 'input'" class="pslot" :inert="mode !== 'input'">
      <slot />
    </div>
    <QuestionStepper
      v-if="mode === 'card' && shown"
      ref="card"
      :key="shown.key"
      v-model="state"
      :questions="shown.questions"
      :keys="active"
      :sending="sending"
      @send="onSend"
      @dismiss="dismiss()"
      @minimize="minimize"
    />
  </div>
</template>

<style scoped>
.pdock {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
}
.pslot {
  transform-origin: 50% 55%;
}
.pchip {
  align-self: center;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  max-width: 100%;
  margin: 0 0 8px;
  padding: 0 6px 0 12px;
  border-radius: var(--r-pill);
  font-size: 13px;
  color: var(--text);
  background: color-mix(in srgb, var(--surface-2) 92%, transparent);
  box-shadow: inset 0 0 0 1px var(--accent-line), 0 10px 28px -16px var(--accent);
  backdrop-filter: blur(10px);
  transition: background 0.2s, scale 0.35s var(--spring), box-shadow 0.3s;
}
.pchip:hover {
  background: var(--surface-hover);
}
.pchip:active {
  scale: var(--press-scale);
}
.pmin {
  align-self: stretch;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 40px;
  margin: 0 0 8px;
  padding: 0 12px;
  border-radius: 12px;
  font-size: 13px;
  text-align: left;
  color: var(--text);
  background: color-mix(in srgb, var(--accent) 10%, var(--surface-2));
  box-shadow: inset 0 0 0 1px var(--accent-line), 0 8px 22px -16px var(--accent);
  transition: background 0.2s, scale 0.35s var(--spring);
}
.pmin .ptxt { flex: 1; }
.pmin .up { flex: none; rotate: -90deg; color: var(--accent); }
.pmin:hover { background: color-mix(in srgb, var(--accent) 16%, var(--surface-2)); }
.pmin:active { scale: 0.985; }
:root[data-motion='soft'] .pmin { transition: none; }
.dot {
  flex: none;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  position: relative;
  background: var(--accent);
}
.dot::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.6;
  pointer-events: none;
  animation: ping 1.8s var(--ease-out) infinite;
}
@keyframes ping {
  0% { transform: scale(1); opacity: 0.6; }
  70%, 100% { transform: scale(3); opacity: 0; }
}
:root[data-motion='soft'] .dot::after { animation: none; }
.ptxt {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 550;
}
.pgo {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent);
}
.chip-enter-active { transition: opacity 0.3s, transform 0.55s var(--spring); }
.chip-leave-active { transition: opacity 0.15s, transform 0.2s; }
.chip-enter-from { opacity: 0; transform: translateY(10px) scale(0.9); }
.chip-leave-to { opacity: 0; transform: scale(0.95); }
@media (pointer: coarse) {
  .pchip { min-height: 44px; }
}
</style>
