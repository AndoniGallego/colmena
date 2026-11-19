<script setup lang="ts">
import { ref } from 'vue'
import { copyText } from '../lib/clipboard'
import { useConfirmacionBoton } from '../lib/confirmacionBoton'
import Icon from './Icon.vue'

const props = defineProps<{ text: string | (() => string); label?: string; primary?: boolean; icon?: boolean }>()
const btn = ref<HTMLButtonElement | null>(null)
const confirmacion = useConfirmacionBoton(1500)
const { hecho: done, error, fallo, pulsarHecho } = confirmacion
const path = confirmacion.path

async function copy() {
  const text = typeof props.text === 'function' ? props.text() : props.text
  error.value = ''
  if (!(await copyText(text))) {
    fallo('No pude copiar', btn.value)
    return
  }
  await pulsarHecho(path)
}
</script>

<template>
  <button ref="btn" class="cbtn" :class="{ primary, done, ico: icon, err: !!error }" type="button" :aria-label="label ?? 'Copiar'" @click="copy">
    <span class="gl">
      <Transition name="sw" mode="out-in">
        <svg v-if="done" key="ok" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
          <path ref="path" d="m5 12.5 4.5 4.5L19 7.5" />
        </svg>
        <Icon v-else key="cp" name="copy" :size="15" />
      </Transition>
    </span>
    <span v-if="label && !icon" class="lb">{{ done ? 'Copiado' : error || label }}</span>
    <span v-if="error && icon" class="lb err" role="alert">{{ error }}</span>
  </button>
</template>

<style scoped>
.cbtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  min-height: 34px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  border: 1px solid var(--line-2);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 540;
  transition: background 0.2s, border-color 0.2s, color 0.2s, scale 0.3s var(--spring);
}
.cbtn.ico { width: 34px; padding: 0; }
.cbtn:hover { background: var(--surface-hover); border-color: var(--accent-line); color: var(--text); }
.cbtn:active { scale: var(--press-scale); }
.cbtn.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-ink); }
.cbtn.primary:hover { filter: brightness(1.08); }
.cbtn.done { color: var(--st-done); border-color: var(--st-done); }
.cbtn.err { color: var(--danger); border-color: color-mix(in srgb, var(--danger) 55%, transparent); }
.lb.err { position: absolute; top: calc(100% + 4px); left: 50%; transform: translateX(-50%); white-space: nowrap; font-size: 11px; color: var(--danger); }
.cbtn.primary.done { background: var(--st-done); border-color: var(--st-done); color: var(--bg); }
.gl { display: grid; place-items: center; width: 15px; height: 15px; }
.sw-enter-active, .sw-leave-active { transition: opacity 0.12s, transform 0.2s var(--spring); }
.sw-enter-from, .sw-leave-to { opacity: 0; transform: scale(0.6); }
</style>
