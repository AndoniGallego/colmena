<script setup lang="ts">
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { normalizarLector } from '../../lib/reunionPuente'
import { auth } from '../../state/app'
import { cargarEstado, fijarEnVentana, reunion } from '../../state/reunion'
import NotchLogin from './NotchLogin.vue'
import NotchReunion from './NotchReunion.vue'

let soltarLector: (() => void) | null = null
let desmontado = false

/** El lector vive en el notch: acá solo se refleja su estado (Sin subtítulos, Pausado...). */
async function seguirLector() {
  const tauri = window.__TAURI__
  const invoke = tauri?.core?.invoke
  const listen = tauri?.event?.listen
  if (typeof listen === 'function') {
    const u = await listen('reunion-lector', (e) => {
      const l = normalizarLector((e as { payload?: unknown } | null)?.payload)
      if (l) reunion.value = { ...reunion.value, lector: l.estado }
    }).catch(() => null)
    if (typeof u === 'function') {
      if (desmontado) u()
      else soltarLector = u as () => void
    }
  }
  if (typeof invoke === 'function') {
    const l = normalizarLector({ estado: await invoke('reunion_estado').catch(() => null) })
    if (l) reunion.value = { ...reunion.value, lector: l.estado }
  }
}

onMounted(() => {
  document.documentElement.classList.add('vista-reunion')
  fijarEnVentana(true)
  void seguirLector()
})

onBeforeUnmount(() => {
  desmontado = true
  soltarLector?.()
  fijarEnVentana(false)
  document.documentElement.classList.remove('vista-reunion')
})

// Al abrirse (o al volver la sesión) se pone al día con el back; después siguen los eventos.
watch(
  auth,
  (a) => {
    if (a === 'ready') void cargarEstado()
  },
  { immediate: true },
)
</script>

<template>
  <main class="ventana">
    <NotchLogin v-if="auth === 'login'" />
    <p v-else-if="auth !== 'ready'" class="espera" role="status">Conectando…</p>
    <NotchReunion v-else ventana />
  </main>
</template>

<style>
html.vista-reunion,
html.vista-reunion body {
  height: 100%;
  overflow: hidden;
  background: var(--bg);
}
html.vista-reunion .fx-layer {
  display: none;
}
</style>

<style scoped>
.ventana {
  height: 100dvh;
  box-sizing: border-box;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 10px 12px 12px;
  background: var(--bg);
  color: var(--text);
}
.espera {
  margin: 0;
  padding: 24px 6px;
  font: 500 var(--t-sm) var(--font-ui);
  color: var(--text-3);
}
</style>
