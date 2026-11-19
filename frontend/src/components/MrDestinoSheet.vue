<script setup lang="ts">
import { computed, ref, useId } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { gsap, isSoft, useGsap } from '../motion'
import { cerrarDestino, elegirDestino, mrsDestino } from '../state/mrs'
import InlineAlert from './InlineAlert.vue'

const { run } = useGsap()
const tituloId = `md-title-${useId()}`
const panel = ref<HTMLElement | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)
const open = computed(() => mrsDestino.open)
const queMando = computed(() => (mrsDestino.cual?.tipo === 'hilo' ? 'el comentario' : 'el log del job'))
const ESTADO: Record<string, string> = { idle: 'Esperando', done: 'Esperando', working: 'Trabajando', blocked: 'Espera tu OK' }

const { onKeydown } = useFocusTrap(panel, open, { onEscape: cerrarDestino, initial: () => cancelBtn.value ?? panel.value })
useSheetSwipe(panel, cerrarDestino)

const sheetLayout = () => window.matchMedia('(max-width: 639px)').matches

function onEnter(el: Element, done: () => void) {
  const back = el.querySelector('.sheet-scrim')
  const card = el.querySelector('.md-panel')
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(back, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'power2.out' }, 0)
    if (sheetLayout()) tl.fromTo(card, { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    else tl.fromTo(card, { y: 24, scale: 0.96, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.55, ease: 'expo.out' }, 0)
  })
}
function onLeave(el: Element, done: () => void) {
  const card = el.querySelector('.md-panel')
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.to(el.querySelector('.sheet-scrim'), { opacity: 0, duration: 0.22 }, 0)
    if (sheetLayout()) tl.to(card, { yPercent: 100, duration: 0.3, ease: 'power3.in' }, 0)
    else tl.to(card, { y: 14, scale: 0.97, opacity: 0, duration: 0.22, ease: 'power2.in' }, 0)
  })
}
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="onEnter" @leave="onLeave">
      <div v-if="open" class="sheet-root md" @keydown="onKeydown">
        <div class="sheet-scrim" @click="cerrarDestino" />
        <section ref="panel" class="sheet-panel md-panel" role="dialog" aria-modal="true" :aria-labelledby="tituloId" tabindex="-1">
          <i class="sheet-grip" aria-hidden="true" />
          <div class="sheet-stagger">
            <h2 :id="tituloId" class="sheet-title">¿A qué sesión le mando {{ queMando }}?</h2>
            <p class="note">Es una sesión de Claude abierta. La sugerida es la que trabaja en la rama de este MR.</p>
            <ul class="lista">
              <li v-for="s in mrsDestino.sesiones" :key="s.session_id">
                <button type="button" class="fila hit" :class="{ sug: s.session_id === mrsDestino.sugerida }" :disabled="mrsDestino.busy" @click="elegirDestino(s.session_id)">
                  <span class="nom">{{ s.nombre }}</span>
                  <span v-if="s.carpeta_corta" class="car mono">{{ s.carpeta_corta }}</span>
                  <span class="tags">
                    <i v-if="s.session_id === mrsDestino.sugerida" class="tag sug-tag">Sugerida</i>
                    <i class="tag">{{ ESTADO[s.status] ?? 'Sin estado' }}</i>
                  </span>
                </button>
              </li>
            </ul>
            <InlineAlert v-if="mrsDestino.error">{{ mrsDestino.error }}</InlineAlert>
            <div class="sheet-actions">
              <button ref="cancelBtn" type="button" class="btn btn-ghost" @click="cerrarDestino">Cancelar</button>
            </div>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.md { z-index: 50; }
.md-panel { outline: none; }
.note { margin: 0; font-size: var(--t-md); line-height: 1.5; color: var(--text-3); }
.lista { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; max-height: min(52vh, 420px); overflow-y: auto; overscroll-behavior: contain; }
.fila { width: 100%; display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 2px 10px; align-items: center; min-height: 52px; padding: 8px 12px; border-radius: var(--r-md); text-align: left; background: var(--bg-2); border: 1px solid var(--line); transition: background 0.2s, border-color 0.2s, scale 0.3s var(--spring), opacity 0.2s; }
.fila:hover:not(:disabled) { background: var(--surface-hover); }
.fila:active:not(:disabled) { scale: var(--press-scale); }
.fila:disabled { opacity: 0.55; cursor: default; }
.fila.sug { border-color: var(--accent-line); background: var(--accent-soft); }
.nom { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--t-lg); font-weight: 580; color: var(--text); }
.car { grid-column: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--t-sm); color: var(--text-3); }
.tags { grid-column: 2; grid-row: 1 / span 2; display: flex; gap: 5px; align-items: center; }
.tag { font-style: normal; font-size: var(--t-xs); font-weight: 600; padding: 2px 8px; border-radius: var(--r-pill); color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
.tag.sug-tag { color: var(--accent); background: var(--accent-soft); box-shadow: none; }
</style>
