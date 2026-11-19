<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { ApiError } from '../../api/types'
import { login } from '../../state/app'

const pin = ref('')
const busy = ref(false)
const error = ref<string | null>(null)
const lockedUntil = ref<number | null>(null)
const now = ref(Date.now())
let tick: ReturnType<typeof setInterval> | undefined

const remaining = computed(() =>
  lockedUntil.value ? Math.max(0, Math.ceil((lockedUntil.value - now.value) / 1000)) : 0,
)
const locked = computed(() => remaining.value > 0)

function startLock(seconds: number) {
  lockedUntil.value = Date.now() + seconds * 1000
  clearInterval(tick)
  tick = setInterval(() => {
    now.value = Date.now()
    if (!locked.value) {
      clearInterval(tick)
      lockedUntil.value = null
      error.value = null
    }
  }, 1000)
}

onBeforeUnmount(() => clearInterval(tick))

async function submit() {
  if (!pin.value || busy.value || locked.value) return
  busy.value = true
  error.value = null
  try {
    await login(pin.value)
    pin.value = ''
  } catch (e) {
    pin.value = ''
    if (e instanceof ApiError && e.status === 429) {
      const sec = e.retryAfter ?? 600
      startLock(sec)
      error.value = `Demasiados intentos. Probá en ${Math.ceil(sec / 60)} min`
    } else if (e instanceof ApiError && e.status === 401) {
      error.value = 'PIN incorrecto'
    } else {
      error.value = 'No llego al servidor'
    }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <form class="login" @submit.prevent="submit">
    <label class="lbl">
      <span>PIN</span>
      <input
        v-model="pin"
        type="password"
        inputmode="numeric"
        autocomplete="current-password"
        :disabled="busy || locked"
      />
    </label>
    <p v-if="error" class="err">{{ error }}</p>
    <button type="submit" :disabled="!pin || busy || locked">Entrar</button>
  </form>
</template>

<style scoped>
.login {
  display: grid;
  gap: 10px;
  padding: 4px 6px 8px;
}
.lbl {
  display: grid;
  gap: 4px;
  font-size: 0.74rem;
  color: var(--text-3);
}
.lbl input {
  font: inherit;
  font-size: 0.9rem;
  color: var(--text);
  background: var(--surface-2);
  border: 1px solid var(--line);
  border-radius: var(--r-md);
  padding: 8px 10px;
}
.lbl input:focus {
  outline: none;
  border-color: var(--accent-line);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.err {
  margin: 0;
  font-size: 0.78rem;
  color: var(--st-blocked);
}
button {
  font: inherit;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent);
  border: 0;
  border-radius: var(--r-md);
  padding: 8px 12px;
  cursor: pointer;
}
button:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
