<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { useKeyboard } from '../lib/keyboard'
import { pinCopy } from '../lib/dialogo'
import { closePin, confirmPin, dlg } from '../state/dialogo'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'

const { run } = useGsap()
const kb = useKeyboard()
const panel = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const pin = ref('')
const now = ref(Date.now())
let tick: ReturnType<typeof setInterval> | undefined

const open = computed(() => dlg.pin.open)
const { onKeydown } = useFocusTrap(panel, open, { onEscape: closePin, initial: () => input.value })
useSheetSwipe(panel, closePin)
const busy = computed(() => dlg.phase === 'sending' || dlg.phase === 'verifying')
const copy = computed(() => pinCopy(dlg.pin.choice ?? 'si_siempre', dlg.pin.regla))
const isMode = computed(() => dlg.pin.choice === 'si_auto' || dlg.pin.choice === 'si_ediciones')
const remaining = computed(() => (dlg.pin.lockedUntil ? Math.max(0, Math.ceil((dlg.pin.lockedUntil - now.value) / 1000)) : 0))
const locked = computed(() => remaining.value > 0)
const remainingLabel = computed(() => (remaining.value >= 60 ? `${Math.ceil(remaining.value / 60)} min` : `${remaining.value} s`))

watch(open, (on) => {
  pin.value = ''
  clearInterval(tick)
  if (!on) return
})
watch(
  () => dlg.pin.lockedUntil,
  (until) => {
    clearInterval(tick)
    if (!until) return
    now.value = Date.now()
    tick = setInterval(() => {
      now.value = Date.now()
      if (now.value >= until) {
        clearInterval(tick)
        dlg.pin.lockedUntil = null
        dlg.pin.error = null
      }
    }, 1000)
  },
)
onBeforeUnmount(() => {
  clearInterval(tick)
  pin.value = ''
})

async function submit() {
  if (!pin.value || busy.value || locked.value) return
  const value = pin.value
  pin.value = ''
  await confirmPin(value)
  if (dlg.pin.open) {
    await nextTick()
    input.value?.focus()
  }
}

const layout = computed(() => (kb.open.value && kb.height.value ? { height: `${kb.height.value}px`, top: `${kb.top.value}px` } : undefined))

function onEnter(el: Element, done: () => void) {
  const back = el.querySelector('.sheet-scrim')
  const card = el.querySelector('.ps-panel')
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(back, { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0)
    tl.fromTo(card, { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    tl.from(el.querySelectorAll('.ps-stagger > *'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', stagger: 0.05 }, 0.18)
  })
}
function onLeave(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.to(el.querySelector('.sheet-scrim'), { opacity: 0, duration: 0.22 }, 0)
    tl.to(el.querySelector('.ps-panel'), { yPercent: 100, duration: 0.3, ease: 'power3.in' }, 0)
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="onEnter" @leave="onLeave">
      <div v-if="open" class="sheet-root ps" :style="layout" @keydown="onKeydown">
        <div class="sheet-scrim ps-back" @click="closePin" />
        <form ref="panel" class="sheet-panel ps-panel" role="dialog" aria-modal="true" aria-labelledby="ps-title" @submit.prevent="submit">
          <i class="sheet-grip grip" aria-hidden="true" />
          <div class="sheet-stagger ps-stagger">
            <h2 id="ps-title" class="sheet-title title"><Icon name="lock" :size="17" /> Confirmá con tu PIN</h2>
            <p class="note" :class="{ mode: isMode }">
              <Icon v-if="isMode" name="warn" :size="15" />
              <span>{{ copy.note }}<template v-if="copy.code"> <code>{{ copy.code }}</code>.</template><template v-if="copy.tail"> {{ copy.tail }}</template> Pide el PIN porque vale más allá de este pedido.</span>
            </p>
            <input
              ref="input"
              v-model="pin"
              class="pin"
              type="password"
              inputmode="numeric"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              enterkeyhint="done"
              placeholder="PIN"
              aria-label="PIN"
              :disabled="busy || locked"
            />
            <p v-if="dlg.pin.error" class="problem" role="alert">
              <Icon name="warn" :size="14" />
              <span>{{ dlg.pin.error }}<template v-if="locked"> Probá de nuevo en {{ remainingLabel }}.</template></span>
            </p>
            <div class="sheet-actions actions">
              <button type="submit" class="btn btn-danger" :class="{ spinning: busy }" :disabled="!pin || busy || locked" :aria-busy="busy">
                <span v-if="busy" class="spin" aria-hidden="true" />{{ busy ? (dlg.phase === 'verifying' ? 'Verificando…' : 'Enviando…') : copy.confirm }}
              </button>
              <button type="button" class="btn btn-ghost" :disabled="busy" @click="closePin">Cancelar</button>
            </div>
          </div>
        </form>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ps {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  height: 100dvh;
  z-index: 60;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.ps-panel {
  position: relative;
  width: min(100%, 520px);
  max-height: 100%;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 10px 18px calc(18px + env(safe-area-inset-bottom));
  border-radius: 20px 20px 0 0;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-bottom: 0;
  box-shadow: var(--shadow-pop);
}
.grip {
  display: block;
  width: 38px;
  height: 4px;
  border-radius: 4px;
  margin: 0 auto 12px;
  background: var(--line-2);
}
.ps-stagger {
  display: grid;
  gap: 12px;
}
.title {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
.note {
  margin: 0;
  font-size: var(--t-lg);
  line-height: 1.5;
  color: var(--text-2);
}
.note.mode {
  display: flex;
  align-items: flex-start;
  gap: 9px;
  padding: 10px 12px;
  border-radius: var(--r-md);
  color: var(--text);
  background: var(--st-blocked-soft);
  border: 1px solid color-mix(in srgb, var(--st-blocked) 35%, transparent);
}
.note.mode svg {
  flex: none;
  margin-top: 2px;
  color: var(--st-blocked);
}
.note code {
  font-family: var(--font-mono);
  font-size: var(--t-md);
  color: var(--text);
  overflow-wrap: anywhere;
}
.pin {
  width: 100%;
  height: 50px;
  padding: 0 14px;
  border-radius: 12px;
  font: inherit;
  font-size: 18px;
  letter-spacing: 0.3em;
  color: var(--text);
  background: var(--bg-2);
  border: 1px solid var(--line-2);
  outline: none;
  transition: border-color 0.2s, box-shadow 0.25s;
}
.pin::placeholder {
  letter-spacing: 0;
  color: var(--text-4);
}
.pin:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent);
}
.problem {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin: 0;
  padding: 9px 12px;
  border-radius: var(--r-md);
  font-size: 13px;
  line-height: 1.4;
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
}
.problem svg {
  flex: none;
  margin-top: 2px;
}
.actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
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
.danger {
  background: var(--danger);
  color: var(--danger-ink);
}
.ghost {
  color: var(--text-2);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
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
  .ps {
    align-items: center;
  }
  .ps-panel {
    border-radius: 20px;
    border-bottom: 1px solid var(--line-2);
    padding: 22px 24px;
    max-height: min(86dvh, 720px);
  }
  .grip {
    display: none;
  }
}
</style>
