<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ApiError } from '../api/types'
import { login } from '../state/app'
import { gsap, haptic, isSoft, SplitText, unlocked, useGsap, vMagnetic } from '../motion'
import Icon from './Icon.vue'
import BrandLockup from './BrandLockup.vue'

const pin = ref('')
const { run } = useGsap()
const card = ref<HTMLElement | null>(null)
const title = ref<HTMLElement | null>(null)
const field = ref<HTMLElement | null>(null)
const dotsEl = ref<HTMLElement | null>(null)
const scan = ref<HTMLElement | null>(null)
const focused = ref(false)
const accepted = ref(false)
const MAX_DOTS = 12
const dotCount = computed(() => Math.min(pin.value.length, MAX_DOTS))

const busy = ref(false)
const error = ref<string | null>(null)
const lockedUntil = ref<number | null>(null)
const now = ref(Date.now())
const input = ref<HTMLInputElement | null>(null)
let tick: ReturnType<typeof setInterval> | undefined

const remaining = computed(() => (lockedUntil.value ? Math.max(0, Math.ceil((lockedUntil.value - now.value) / 1000)) : 0))
const locked = computed(() => remaining.value > 0)
const remainingLabel = computed(() => {
  const s = remaining.value
  return s >= 60 ? `${Math.ceil(s / 60)} min` : `${s} s`
})
const srLockMsg = ref<string | null>(null)

function startLock(seconds: number) {
  srLockMsg.value = `Probá de nuevo en ${seconds} segundos`
  lockedUntil.value = Date.now() + seconds * 1000
  clearInterval(tick)
  tick = setInterval(() => {
    now.value = Date.now()
    if (!locked.value) {
      clearInterval(tick)
      lockedUntil.value = null
      error.value = null
      srLockMsg.value = null
      nextTick(() => input.value?.focus())
    }
  }, 1000)
}

async function submit() {
  if (!pin.value || busy.value || locked.value) return
  busy.value = true
  error.value = null
  try {
    await login(pin.value, unlock)
  } catch (e) {
    if (e instanceof ApiError && e.status === 401) await reject()
    pin.value = ''
    if (e instanceof ApiError && e.status === 429) {
      startLock(e.retryAfter ?? 600)
      error.value = 'Demasiados intentos.'
    } else if (e instanceof ApiError && e.status === 401) {
      error.value = 'PIN incorrecto'
    } else if (e instanceof ApiError && e.status === 403) {
      error.value = 'Esta red no tiene acceso'
    } else {
      error.value = 'No llego al servidor'
    }
    busy.value = false
    nextTick(() => input.value?.focus())
  }
}

watch(dotCount, async (n, o) => {
  if (n <= o) return
  await nextTick()
  const fresh = [...(dotsEl.value?.children ?? [])].slice(o, n)
  if (!fresh.length) return
  if (isSoft()) {
    run(() => gsap.from(fresh, { opacity: 0, duration: 0.15 }))
    return
  }
  run(() =>
    gsap.fromTo(
      fresh,
      { scale: 0, y: 10, opacity: 0 },
      { scale: 1, y: 0, opacity: 1, duration: 0.55, ease: 'elastic.out(1.1, 0.45)', stagger: 0.04 },
    ),
  )
  haptic(6)
})

function reject() {
  haptic([30, 40, 30])
  return new Promise<void>((done) => {
    run(() => {
      const tl = gsap.timeline({ onComplete: done })
      const dots = [...(dotsEl.value?.children ?? [])]
      if (isSoft()) {
        tl.to(dots, { opacity: 0, duration: 0.15 })
        return
      }
      tl.to(field.value, { keyframes: { x: [0, -10, 9, -6, 4, -2, 0] }, duration: 0.48, ease: 'none' }, 0)
      tl.to(dots, { y: 14, opacity: 0, scale: 0.4, duration: 0.32, ease: 'power2.in', stagger: { each: 0.03, from: 'end' } }, 0.06)
    })
  })
}

function unlock() {
  accepted.value = true
  haptic([10, 50, 18])
  return new Promise<void>((done) => {
    const finish = () => {
      unlocked.value = true
      done()
    }
    run(() => {
      const dots = [...(dotsEl.value?.children ?? [])]
      if (isSoft()) {
        gsap.timeline({ onComplete: finish }).to(card.value, { opacity: 0, duration: 0.25, delay: 0.15 })
        return
      }
      const fr = field.value!.getBoundingClientRect()
      const cx = fr.left + fr.width / 2
      const tl = gsap.timeline()
      tl.add(finish, 0.98)
      tl.to(dots, { scale: 1.35, duration: 0.18, ease: 'power2.out', stagger: 0.035 }, 0)
        .to(dots, { scale: 1, duration: 0.3, ease: 'back.out(3)', stagger: 0.035 }, 0.18)
        .to(
          dots,
          {
            x: (_i: number, el: Element) => {
              const r = el.getBoundingClientRect()
              return cx - (r.left + r.width / 2)
            },
            scale: 0.2,
            opacity: 0,
            duration: 0.38,
            ease: 'power3.in',
            stagger: { each: 0.02, from: 'edges' },
          },
          0.5,
        )
        .fromTo(scan.value, { top: fr.top + fr.height / 2, scaleX: 0, opacity: 1 }, { scaleX: 1, duration: 0.42, ease: 'expo.out' }, 0.78)
        .to(card.value, { y: -18, scale: 0.97, opacity: 0, duration: 0.45, ease: 'power3.in' }, 0.8)
        .to(scan.value, { scaleY: 40, opacity: 0, duration: 0.5, ease: 'power2.out' }, 1.08)
    })
  })
}

onMounted(() => {
  input.value?.focus()
  if (!card.value) return
  if (isSoft()) {
    run(() => gsap.from(card.value, { opacity: 0, duration: 0.3 }))
    return
  }
  run(() => {
    const split = title.value ? SplitText.create(title.value, { type: 'words,chars', mask: 'words' }) : null
    const q = gsap.utils.selector(card.value)
    // Un from() interrumpido o repetido deja opacity:0 pegado en línea.
    const tl = gsap.timeline({ defaults: { ease: 'expo.out', clearProps: 'opacity,transform,scale,rotate,translate' }, onComplete: () => split?.revert() })
    tl.from(q('.brand'), { y: 12, opacity: 0, duration: 0.8 }, 0)
    if (split) tl.from(split.chars, { yPercent: 110, duration: 0.9, stagger: 0.022 }, 0.12)
    tl.from(q('.sub'), { y: 10, opacity: 0, duration: 0.8 }, 0.38)
      .from(field.value, { y: 18, opacity: 0, scale: 0.97, duration: 1, ease: 'orq.spring' }, 0.46)
      .from(q('.go'), { scale: 0.4, rotation: -30, opacity: 0, duration: 0.7, ease: 'back.out(2.2)' }, 0.66)
  })
})
onBeforeUnmount(() => clearInterval(tick))
</script>

<template>
  <div class="login">
    <i ref="scan" class="scan" aria-hidden="true" />
    <form ref="card" class="card" @submit.prevent="submit">
      <div class="brand">
        <BrandLockup :size="34" />
      </div>
      <h1 ref="title">Entrá con tu PIN</h1>
      <p class="sub">Tus sesiones de Claude, en vivo.</p>

      <label ref="field" class="field" :class="{ error: !!error, locked, accepted, focused }">
        <Transition name="icon-swap" mode="out-in">
          <Icon :key="accepted ? 'ok' : 'lock'" :name="accepted ? 'check' : 'lock'" :size="17" class="field-icon" />
        </Transition>
        <span class="pin-view" aria-hidden="true">
          <span ref="dotsEl" class="dots"><i v-for="i in dotCount" :key="i" class="dot" /></span>
          <i v-if="focused && !busy && !accepted" class="pin-caret" :class="{ empty: !pin }" />
        </span>
        <span class="sr-only">PIN</span>
        <input
          ref="input"
          v-model="pin"
          type="password"
          inputmode="numeric"
          autocomplete="current-password"
          maxlength="32"
          placeholder="••••"
          :disabled="busy || locked"
          @input="error = locked ? error : null"
          @focus="focused = true"
          @blur="focused = false"
        />
        <button v-magnetic="0.3" type="submit" class="go" :disabled="!pin || busy || locked" aria-label="Entrar">
          <span v-if="busy" class="spinner" />
          <Icon v-else name="arrow-right" :size="17" />
        </button>
      </label>

      <p class="msg" :class="{ show: !!error || locked }">
        <span v-if="error" role="alert">{{ error }}</span>
        <template v-if="locked">
          <span aria-hidden="true"> Probá de nuevo en <span class="mono">{{ remainingLabel }}</span>.</span>
          <span v-if="srLockMsg" class="sr-only">{{ srLockMsg }}</span>
        </template>
      </p>
    </form>
  </div>
</template>

<style scoped>
/* Con el teclado de iOS abierto mide lo visible: si el form queda debajo, iOS y useKeyboard se pelean el scroll. */
.login {
  height: var(--app-h, 100dvh);
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  place-items: center;
  padding: calc(24px + env(safe-area-inset-top)) 16px calc(24px + env(safe-area-inset-bottom));
  background:
    radial-gradient(700px 380px at 50% 0%, var(--accent-soft), transparent 70%),
    var(--bg);
}
.login {
  position: relative;
  overflow: hidden;
}
.card {
  position: relative;
  z-index: 1;
  width: min(380px, 100%);
}
.scan {
  position: fixed;
  left: 0;
  right: 0;
  top: 50%;
  height: 2px;
  margin-top: -1px;
  z-index: 2;
  opacity: 0;
  pointer-events: none;
  background: linear-gradient(90deg, transparent, var(--accent) 20%, #fff 50%, var(--accent) 80%, transparent);
  box-shadow: 0 0 18px 2px var(--accent), 0 0 60px 6px var(--accent-soft);
  transform: scaleX(0);
}
.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 44px;
}
.login.kb-open {
  position: fixed;
  left: 0;
  right: 0;
  top: var(--vv-top, 0px);
}
.kb-open .brand {
  margin-bottom: 20px;
}
h1 {
  font-family: var(--font-display);
  font-size: 34px;
  line-height: 1.02;
  letter-spacing: -0.03em;
  font-weight: 600;
  margin: 0 0 8px;
}
.sub {
  color: var(--text-3);
  margin: 0 0 28px;
}
.field {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 6px 6px 16px;
  border-radius: var(--r-lg);
  background: var(--surface);
  border: 1px solid var(--line-2);
  transition: border-color 0.25s, box-shadow 0.3s var(--ease-out), background 0.25s;
}
.field:focus-within {
  border-color: var(--accent-line);
  box-shadow: 0 0 0 4px var(--accent-soft);
}
.field.error {
  border-color: color-mix(in srgb, var(--danger) 60%, transparent);
}
.field.accepted {
  border-color: var(--accent);
  box-shadow: 0 0 0 4px var(--accent-soft), 0 0 32px -6px var(--accent);
}
.field.accepted .field-icon {
  color: var(--accent);
}
.pin-view {
  position: absolute;
  left: 44px;
  right: 60px;
  top: 0;
  bottom: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  pointer-events: none;
  overflow: hidden;
}
.dots {
  display: flex;
  align-items: center;
  gap: 9px;
}
.dot {
  width: 11px;
  height: 11px;
  border-radius: 50%;
  background: var(--text);
}
.error .dot {
  background: var(--danger);
}
.accepted .dot {
  background: var(--accent);
  box-shadow: 0 0 12px var(--accent);
}
.pin-caret {
  width: 2px;
  height: 22px;
  margin-left: 6px;
  border-radius: 1px;
  background: var(--accent);
  animation: caret 1.05s steps(2, jump-none) infinite;
}
.pin-caret.empty {
  margin-left: 0;
  position: absolute;
  left: 0;
}
@keyframes caret {
  50% { opacity: 0; }
}
.field.locked {
  opacity: 0.6;
}
.field-icon {
  color: var(--text-3);
  flex: none;
}
input {
  flex: 1;
  min-width: 0;
  border: 0;
  outline: none !important;
  background: none;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 22px;
  letter-spacing: 0.35em;
  padding: 8px 0;
  color: transparent;
  caret-color: transparent;
}
.focused input::placeholder {
  opacity: 0;
}
input::placeholder {
  color: var(--text-4);
}
.go {
  flex: none;
  width: 44px;
  height: 44px;
  border-radius: var(--r-md);
  display: grid;
  place-items: center;
  background: var(--accent);
  color: var(--accent-ink);
  transition: translate 0.25s var(--spring), scale 0.25s var(--spring), opacity 0.2s, filter 0.2s, box-shadow 0.3s;
}
.go:hover:not(:disabled) {
  translate: 2px 0;
  box-shadow: 0 0 0 4px var(--accent-soft), 0 6px 22px -6px var(--accent);
}
.go:active:not(:disabled) {
  scale: var(--press-scale);
}
.go:disabled {
  opacity: 0.35;
  cursor: default;
}
.spinner {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  border: 2px solid currentColor;
  border-right-color: transparent;
  animation: spin 0.7s linear infinite;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.msg {
  min-height: 22px;
  margin: 12px 2px 0;
  font-size: var(--t-lg);
  color: var(--danger);
  opacity: 0;
  transform: translateY(-4px);
  transition: opacity 0.25s, transform 0.3s var(--ease-out);
}
.msg.show {
  opacity: 1;
  transform: none;
}
:root[data-motion='soft'] .pin-caret {
  animation: none;
}
</style>
