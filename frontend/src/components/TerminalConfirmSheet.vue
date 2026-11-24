<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { notaCierre, verInvisibles } from '../lib/terminales'
import { act, confirmAccion, dismissAccion, openAccion } from '../state/terminalActions'
import { gsap, isSoft, useGsap } from '../motion'
import Icon from './Icon.vue'
import ListoOverlay from './ListoOverlay.vue'

const { run } = useGsap()
const panel = ref<HTMLElement | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)
const open = computed(() => act.kind !== null)
const isCtrl = computed(() => act.kind === 'ctrl-c')
const loading = computed(() => act.phase === 'loading')
const busy = computed(() => act.phase === 'running')
const p = computed(() => act.preview)
const where = computed(() => (p.value ? [p.value.workspace, p.value.tab].filter(Boolean).join(' · ') : ''))
const isCerrar = computed(() => act.kind === 'cerrar')
const title = computed(() => (isCtrl.value ? '¿Mandar Ctrl+C?' : isCerrar.value ? '¿Cerrar esta terminal?' : act.kind === 'comando' ? '¿Ejecutar este comando?' : '¿Repetir el último comando?'))
const line = computed(() => (act.kind === 'comando' ? verInvisibles(act.comando) : act.prep?.linea ?? ''))
const primary = computed(() => (busy.value ? (isCerrar.value ? 'Cerrando…' : 'Enviando…') : isCtrl.value ? 'Mandar Ctrl+C' : isCerrar.value ? 'Cerrar terminal' : 'Ejecutar'))
const { onKeydown } = useFocusTrap(panel, open, {
  onEscape: dismissAccion,
  initial: () => cancelBtn.value ?? panel.value,
})
useSheetSwipe(panel, dismissAccion)

const sheetLayout = () => window.matchMedia('(max-width: 639px)').matches

function onEnter(el: Element, done: () => void) {
  const card = el.querySelector('.ts-panel')
  if (isSoft()) {
    run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
    return
  }
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(el.querySelector('.sheet-scrim'), { opacity: 0 }, { opacity: 1, duration: 0.3 }, 0)
    if (sheetLayout()) tl.fromTo(card, { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    else tl.fromTo(card, { y: 24, scale: 0.96, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.55, ease: 'expo.out' }, 0)
    tl.from(el.querySelectorAll('.ts-stagger > *'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', stagger: 0.05 }, 0.18)
  })
}
function onLeave(el: Element, done: () => void) {
  const card = el.querySelector('.ts-panel')
  if (isSoft()) {
    run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
    return
  }
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
      <div v-if="open" class="sheet-root ts" @keydown="onKeydown">
        <div class="sheet-scrim ts-back" @click="dismissAccion" />
        <section ref="panel" class="sheet-panel ts-panel" role="dialog" aria-modal="true" aria-labelledby="ts-title" tabindex="-1">
          <i class="sheet-grip grip" aria-hidden="true" />
          <div class="sheet-stagger ts-stagger">
            <h2 id="ts-title" class="sheet-title title">{{ title }}</h2>

            <div v-if="loading" class="skeleton" aria-busy="true" aria-label="Cargando"><i class="sk-sweep" /><i class="sk-sweep" /></div>

            <div v-if="p" class="target">
              <p class="where mono">{{ where }}</p>
              <p class="name">{{ p.titulo || p.proceso || 'Terminal' }}</p>
              <p class="cwd mono">{{ p.cwd }}</p>
              <span class="chip mono" :class="p.estado"><i class="dot" />{{ p.estado === 'prompt' ? 'en el prompt' : p.proceso || 'sin datos' }}</span>
            </div>

            <div v-if="line" class="line">
              <span class="label mono">se va a ejecutar</span>
              <code>{{ line }}</code>
            </div>
            <p v-else-if="isCtrl && p && !act.error" class="note">Corta el programa que está corriendo en esta terminal. No se puede deshacer.</p>
            <p v-else-if="isCerrar && p && !act.error && p.estado !== 'prompt'" class="note">
              Está corriendo <strong class="mono">{{ p.proceso || 'un programa' }}</strong>. Cerrar la terminal lo corta y no se puede deshacer.
            </p>
            <p v-if="isCerrar && p && !act.error && notaCierre(p)" class="note">{{ notaCierre(p) }}</p>

            <p v-if="act.error" class="problem" role="alert"><Icon name="warn" :size="14" /> <span>{{ act.error }}</span></p>

            <div class="sheet-actions actions">
              <button v-if="act.phase !== 'error'" type="button" class="btn btn-primary" :class="{ spinning: busy }" :disabled="act.phase !== 'ready'" :aria-busy="busy" @click="confirmAccion">
                <span v-if="busy || loading" class="spin" aria-hidden="true" />{{ loading ? 'Revisando…' : primary }}
              </button>
              <button v-else type="button" class="btn btn-primary" @click="openAccion(act.kind!, act.paneId)"><Icon name="refresh" :size="14" /> Revisar de nuevo</button>
              <button ref="cancelBtn" type="button" class="btn btn-ghost" :disabled="busy" @click="dismissAccion">{{ act.phase === 'error' ? 'Cerrar' : 'Cancelar' }}</button>
            </div>
          </div>
          <ListoOverlay :visible="act.listo" :texto="act.listoTxt" />
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ts { position: fixed; inset: 0; z-index: 50; display: flex; align-items: flex-end; justify-content: center; }
@media (min-width: 640px) {
  .ts { align-items: center; }
  .ts-panel { position: relative; border-radius: 20px; border-bottom: 1px solid var(--line-2); padding-bottom: 18px; }
  .grip { display: none; }
}
.grip { display: block; width: 38px; height: 4px; border-radius: 4px; margin: 0 auto 12px; background: var(--line-2); }
.ts-stagger { display: grid; gap: 12px; }
.title { margin: 0; font-family: var(--font-display); font-size: 19px; font-weight: 600; letter-spacing: -0.02em; line-height: 1.25; }
.target { display: grid; gap: 3px; padding: 11px 13px; border-radius: 12px; background: var(--bg-2); border: 1px solid var(--line); min-width: 0; }
.target p { margin: 0; min-width: 0; overflow-wrap: anywhere; }
.where { font-size: 11px; color: var(--text-4); }
.name { font-size: 14.5px; font-weight: 600; }
.cwd { font-size: var(--t-sm); color: var(--text-3); }
.chip { justify-self: start; margin-top: 5px; display: inline-flex; align-items: center; gap: 6px; height: 22px; padding: 0 9px; border-radius: var(--r-pill); font-size: 11px; color: var(--text-2); background: var(--st-idle-soft); }
.chip .dot { width: 6px; height: 6px; border-radius: 50%; background: var(--st-idle); }
.chip.corriendo { color: var(--st-working); background: var(--st-working-soft); }
.chip.corriendo .dot { background: var(--st-working); }
.chip.prompt .dot { background: var(--st-done); }
.line { display: grid; gap: 6px; padding: 11px 13px; border-radius: 12px; background: var(--term-bg); box-shadow: inset 0 0 0 1px var(--line-2); }
.label { font-size: var(--t-xs); letter-spacing: 0.12em; text-transform: uppercase; color: var(--text-4); }
.line code { font-family: var(--font-mono); font-size: 13px; color: var(--term-fg); overflow-wrap: anywhere; white-space: pre-wrap; }
.note { margin: 0; font-size: var(--t-md); line-height: 1.5; color: var(--text-3); overflow-wrap: anywhere; }
.note strong { color: var(--text); font-weight: 600; }
.problem { display: flex; align-items: flex-start; gap: 8px; margin: 0; padding: 9px 12px; border-radius: var(--r-md); font-size: 13px; line-height: 1.4; color: var(--danger); background: var(--danger-soft); border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent); }
.problem span { min-width: 0; overflow-wrap: anywhere; }
.problem svg { flex: none; margin-top: 2px; }
.skeleton { display: grid; gap: 6px; }
.skeleton i { height: 40px; border-radius: var(--r-md); --sk-bg: linear-gradient(90deg, var(--bg-2), var(--surface-hover), var(--bg-2)); }
.actions { display: flex; flex-direction: column-reverse; gap: 8px; margin-top: 4px; }
@media (min-width: 640px) { .actions { flex-direction: row-reverse; } .actions .btn { flex: 1; } }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 44px; padding: 0 16px; border-radius: 12px; font-size: 14px; font-weight: 600; transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), box-shadow 0.25s, opacity 0.2s; }
.btn:active:not(:disabled) { scale: var(--press-scale); }
.btn:disabled { cursor: not-allowed; }
.go { background: var(--accent); color: var(--accent-ink); }
.go:hover:not(:disabled) { box-shadow: 0 0 0 4px var(--accent-soft), 0 8px 26px -10px var(--accent); }
.go:disabled { background: var(--surface-2); color: var(--text-4); box-shadow: inset 0 0 0 1px var(--line-2); }
.go.busy:disabled { background: var(--accent); color: var(--accent-ink); box-shadow: none; opacity: 0.85; }
.ghost { color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line-2); }
.ghost:hover:not(:disabled) { color: var(--text); background: var(--surface-hover); }
.spin { width: 14px; height: 14px; border-radius: 50%; border: 1.5px solid currentColor; border-right-color: transparent; animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@media (prefers-reduced-motion: reduce) { .spin, .skeleton i::after { animation-duration: 3s; } }
:root[data-motion='soft'] .skeleton i::after {
  animation: none;
}
</style>
