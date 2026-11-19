<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { estiloHoja } from '../lib/capaHoja'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { useKeyboard } from '../lib/keyboard'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import ListoOverlay from './ListoOverlay.vue'

const props = defineProps<{
  open: boolean
  busy: boolean
  error: string | null
  lockedUntil: number | null
  listo?: boolean
  listoTxt?: string
  title?: string
  note?: string
  cta?: string
  danger?: boolean
  capa?: number
}>()
const emit = defineEmits<{ submit: [pin: string]; close: [] }>()

const { run } = useGsap()
const kb = useKeyboard()
const panel = ref<HTMLElement | null>(null)
const input = ref<HTMLInputElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => props.open, {
  onEscape: () => emit('close'),
  initial: () => input.value,
})
useSheetSwipe(panel, () => emit('close'))
const pin = ref('')
const now = ref(Date.now())
let tick: ReturnType<typeof setInterval> | undefined

const remaining = computed(() => (props.lockedUntil ? Math.max(0, Math.ceil((props.lockedUntil - now.value) / 1000)) : 0))
const locked = computed(() => remaining.value > 0)
const remainingLabel = computed(() => (remaining.value >= 60 ? `${Math.ceil(remaining.value / 60)} min` : `${remaining.value} s`))

watch(
  () => props.open,
  (on) => {
    pin.value = ''
    if (!on) return
  },
)
watch(
  () => props.lockedUntil,
  (until) => {
    clearInterval(tick)
    if (!until) return
    now.value = Date.now()
    tick = setInterval(() => {
      now.value = Date.now()
      if (now.value >= until) clearInterval(tick)
    }, 1000)
  },
)
onBeforeUnmount(() => {
  clearInterval(tick)
  pin.value = ''
})

async function submit() {
  if (!pin.value || props.busy || locked.value) return
  const value = pin.value
  pin.value = ''
  emit('submit', value)
  await nextTick()
  input.value?.focus()
}

const layout = computed(() =>
  estiloHoja(kb.open.value && kb.height.value ? { height: `${kb.height.value}px`, top: `${kb.top.value}px` } : undefined, props.capa),
)

function onEnter(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(el.querySelector('.sheet-scrim'), { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0)
    tl.fromTo(el.querySelector('.ps-panel'), { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
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
        <div class="sheet-scrim ps-back" @click="emit('close')" />
        <form ref="panel" class="sheet-panel ps-panel" role="dialog" aria-modal="true" aria-labelledby="tps-title" @submit.prevent="submit">
          <i class="sheet-grip grip" aria-hidden="true" />
          <div class="sheet-stagger ps-stagger">
            <h2 id="tps-title" class="sheet-title title"><Icon name="lock" :size="17" /> {{ title ?? 'Abrí la escritura por 5 minutos' }}</h2>
            <p class="note">
              {{ note ?? 'Con tu PIN se habilita mandar comandos a las terminales durante 5 minutos, o 2 minutos sin usarla. Se cierra sola al salir de la app y cada comando vuelve a pedir confirmación.' }}
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
            <p v-if="error" class="problem" role="alert">
              <Icon name="warn" :size="14" />
              <span>{{ error }}<template v-if="locked"> Probá de nuevo en {{ remainingLabel }}.</template></span>
            </p>
            <div class="sheet-actions actions">
              <button type="submit" class="btn" :class="[danger ? 'btn-danger' : 'btn-primary', { spinning: busy }]" :disabled="!pin || busy || locked" :aria-busy="busy">
                <span v-if="busy" class="spin" aria-hidden="true" />{{ busy ? 'Verificando…' : (cta ?? 'Abrir la escritura') }}
              </button>
              <button type="button" class="btn btn-ghost" :disabled="busy" @click="emit('close')">Cancelar</button>
            </div>
          </div>
          <ListoOverlay :visible="!!listo" :texto="listoTxt || ''" />
        </form>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ps { position: fixed; left: 0; right: 0; top: 0; height: 100dvh; z-index: 60; display: flex; align-items: flex-end; justify-content: center; }
.ps-panel { position: relative; }
.grip { display: block; width: 38px; height: 4px; border-radius: 4px; margin: 0 auto 12px; background: var(--line-2); }
.ps-stagger { display: grid; gap: 12px; }
.title { display: flex; align-items: center; gap: 8px; margin: 0; font-family: var(--font-display); font-size: 19px; font-weight: 600; letter-spacing: -0.02em; }
.note { margin: 0; font-size: var(--t-lg); line-height: 1.5; color: var(--text-2); }
.pin { width: 100%; height: 50px; padding: 0 14px; border-radius: 12px; font: inherit; font-size: 18px; letter-spacing: 0.3em; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; transition: border-color 0.2s, box-shadow 0.25s; }
.pin::placeholder { letter-spacing: 0; color: var(--text-4); }
.pin:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.problem { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 9px 12px; border-radius: var(--r-md); font-size: 13px; line-height: 1.4; color: var(--danger); background: var(--danger-soft); border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent); }
.problem svg { flex: none; margin-top: 2px; }
.actions { display: flex; flex-direction: column-reverse; gap: 8px; margin-top: 4px; }
@media (min-width: 640px) { .actions { flex-direction: row-reverse; } .actions .btn { flex: 1; } }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 44px; padding: 0 16px; border-radius: 12px; font-size: 14px; font-weight: 600; transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), box-shadow 0.25s, opacity 0.2s; }
.btn:active:not(:disabled) { scale: var(--press-scale); }
.btn:disabled { cursor: not-allowed; }
.go { background: var(--accent); color: var(--accent-ink); }
.go:hover:not(:disabled) { box-shadow: 0 0 0 4px var(--accent-soft), 0 8px 26px -10px var(--accent); }
.go:disabled { background: var(--surface-2); color: var(--text-4); box-shadow: inset 0 0 0 1px var(--line-2); }
.go.danger:not(:disabled) { background: var(--danger); color: var(--danger-ink); }
.go.danger:hover:not(:disabled) { box-shadow: 0 0 0 4px var(--danger-soft), 0 8px 26px -10px var(--danger); }
.go.busy:disabled { background: var(--accent); color: var(--accent-ink); box-shadow: none; opacity: 0.85; }
.ghost { color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line-2); }
.ghost:hover:not(:disabled) { color: var(--text); background: var(--surface-hover); }
.spin { width: 14px; height: 14px; border-radius: 50%; border: 1.5px solid currentColor; border-right-color: transparent; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
</style>
