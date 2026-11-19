<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { ATAJO, saltoDeGrupo, tramos, type Resultado } from '../lib/buscador'
import { useFocusTrap } from '../lib/focusTrap'
import { useKeyboard } from '../lib/keyboard'
import { desktop } from '../lib/viewport'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { alternarPaleta, cerrarPaleta, elegir, paleta, planos, resultados } from '../state/buscador'
import Icon from './Icon.vue'

const { run } = useGsap()
const kb = useKeyboard()
const q = ref('')
const sel = ref(0)
const input = ref<HTMLInputElement | null>(null)
const list = ref<HTMLElement | null>(null)
const cursor = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const { onKeydown: trapKeydown } = useFocusTrap(panel, paleta, {
  initial: () => input.value,
  onEscape: () => {
    if (q.value) q.value = ''
    else cerrarPaleta()
  },
})

const secciones = computed(() => resultados(q.value))
const filas = computed(() => planos(secciones.value))
const posiciones = computed(() => {
  const m = new Map<string, number>()
  filas.value.forEach((r, i) => m.set(r.entrada.id, i))
  return m
})
const activa = computed(() => (filas.value[sel.value] ? `pal-${filas.value[sel.value].entrada.id}` : undefined))
const estilo = computed(() => (!desktop.value && kb.open.value && kb.height.value ? { '--pal-max': `${kb.height.value - 14}px`, top: `${kb.top.value}px` } : undefined))

watch(q, () => (sel.value = 0))
watch(filas, () => (sel.value = Math.min(sel.value, Math.max(0, filas.value.length - 1))))

function mover(d: 1 | -1) {
  const n = filas.value.length
  if (n) sel.value = (sel.value + d + n) % n
}

function onKey(e: KeyboardEvent) {
  if (e.isComposing) {
    e.stopPropagation()
    return
  }
  if (e.key === 'Escape') {
    trapKeydown(e)
    return
  }
  if (e.key === 'Tab') {
    e.preventDefault()
    if (filas.value.length) sel.value = saltoDeGrupo(secciones.value, sel.value, e.shiftKey ? -1 : 1)
    return
  }
  if (e.key === 'ArrowDown' || (e.ctrlKey && e.key === 'n')) {
    e.preventDefault()
    mover(1)
  } else if (e.key === 'ArrowUp' || (e.ctrlKey && e.key === 'p')) {
    e.preventDefault()
    mover(-1)
  } else if (e.key === 'Home' && e.ctrlKey) {
    e.preventDefault()
    sel.value = 0
  } else if (e.key === 'End' && e.ctrlKey) {
    e.preventDefault()
    sel.value = Math.max(0, filas.value.length - 1)
  } else if (e.key === 'Enter') {
    e.preventDefault()
    const r = filas.value[sel.value]
    if (r) abrir(r)
  }
}

function abrir(r: Resultado) {
  haptic(6)
  elegir(r.entrada)
}

function onGlobal(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && e.key.toLowerCase() === 'k') {
    e.preventDefault()
    alternarPaleta()
  }
}
onMounted(() => window.addEventListener('keydown', onGlobal, true))
onBeforeUnmount(() => window.removeEventListener('keydown', onGlobal, true))

function ubicarCursor(animar: boolean) {
  const row = list.value?.querySelector<HTMLElement>(`[data-i="${sel.value}"]`)
  const c = cursor.value
  if (!c) return
  if (!row) return void gsap.set(c, { opacity: 0 })
  const to = { y: row.offsetTop, height: row.offsetHeight, opacity: 1 }
  if (animar && !isSoft()) run(() => gsap.to(c, { ...to, duration: 0.26, ease: 'power3.out', overwrite: true }))
  else gsap.set(c, to)
  const box = list.value
  if (!box) return
  const top = row.offsetTop - (row.previousElementSibling?.tagName === 'H3' ? (row.previousElementSibling as HTMLElement).offsetHeight : 0)
  if (top < box.scrollTop) box.scrollTop = top
  else if (row.offsetTop + row.offsetHeight > box.scrollTop + box.clientHeight) box.scrollTop = row.offsetTop + row.offsetHeight - box.clientHeight + 6
}

let vistos = new Set<string>()
watch(
  filas,
  async (now) => {
    await nextTick()
    ubicarCursor(false)
    const fresh = now.filter((r) => !vistos.has(r.entrada.id)).slice(0, 10)
    vistos = new Set(now.map((r) => r.entrada.id))
    if (!fresh.length || isSoft() || !list.value) return
    const els = fresh.map((r) => list.value!.querySelector(`[data-i="${posiciones.value.get(r.entrada.id)}"]`)).filter(Boolean)
    run(() => gsap.from(els, { y: 7, opacity: 0, duration: 0.3, ease: 'power3.out', stagger: 0.02, clearProps: 'transform,opacity' }))
  },
  { flush: 'post' },
)
watch(sel, async () => {
  await nextTick()
  ubicarCursor(true)
})

watch(paleta, (on) => {
  if (on) {
    q.value = ''
    sel.value = 0
    vistos = new Set()
  }
})

async function onEnter(el: Element, done: () => void) {
  await nextTick()
  ubicarCursor(false)
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.16, onComplete: done }))
  const panel = el.querySelector('.pal-panel')
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(el.querySelector('.pal-back'), { opacity: 0 }, { opacity: 1, duration: 0.28 }, 0)
    if (desktop.value) tl.fromTo(panel, { y: -16, scale: 0.965, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.55, ease: 'orq.spring' }, 0)
    else tl.fromTo(panel, { yPercent: -104 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    tl.from(el.querySelectorAll('.pal-in > *'), { y: -6, opacity: 0, duration: 0.4, ease: 'power3.out', stagger: 0.05, clearProps: 'transform,opacity' }, 0.1)
  })
}
function onLeave(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.12, onComplete: done }))
  const panel = el.querySelector('.pal-panel')
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.to(el.querySelector('.pal-back'), { opacity: 0, duration: 0.2 }, 0)
    if (desktop.value) tl.to(panel, { y: -10, scale: 0.975, opacity: 0, duration: 0.18, ease: 'power2.in' }, 0)
    else tl.to(panel, { yPercent: -104, duration: 0.26, ease: 'power3.in' }, 0)
  })
}

</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="onEnter" @leave="onLeave">
      <div v-if="paleta" ref="panel" class="pal" :class="{ wide: desktop }" :style="estilo" @keydown="onKey">
        <div class="pal-back" @click="cerrarPaleta" />
        <div class="pal-panel" role="dialog" aria-modal="true" aria-label="Buscador">
          <div class="pal-in">
            <Icon name="search" :size="18" class="lupa" />
            <input
              ref="input"
              v-model="q"
              class="pal-input"
              type="text"
              role="combobox"
              aria-expanded="true"
              aria-controls="pal-list"
              aria-autocomplete="list"
              :aria-activedescendant="activa"
              placeholder="Buscar sesiones, diagramas, avisos…"
              aria-label="Buscar"
              autocomplete="off"
              autocapitalize="off"
              autocorrect="off"
              spellcheck="false"
              enterkeyhint="go"
            />
            <button v-if="q" class="clear" type="button" aria-label="Borrar búsqueda" @mousedown.prevent @click="q = ''; input?.focus()"><Icon name="close" :size="14" /></button>
            <kbd v-if="desktop" class="esc">Esc</kbd>
            <button v-else class="cancel" type="button" @click="cerrarPaleta">Cerrar</button>
          </div>

          <div id="pal-list" ref="list" class="pal-list" role="listbox" aria-label="Resultados">
            <i ref="cursor" class="cursor" aria-hidden="true" />
            <section v-for="s in secciones" :key="s.grupo" class="grp" role="group" :aria-label="s.titulo">
              <h3>{{ s.titulo }}</h3>
              <button
                v-for="r in s.items"
                :id="`pal-${r.entrada.id}`"
                :key="r.entrada.id"
                class="row"
                :class="{ on: posiciones.get(r.entrada.id) === sel }"
                :data-i="posiciones.get(r.entrada.id)"
                role="option"
                tabindex="-1"
                :aria-selected="posiciones.get(r.entrada.id) === sel"
                @mousedown.prevent
                @pointermove="posiciones.get(r.entrada.id) !== sel && (sel = posiciones.get(r.entrada.id) ?? sel)"
                @click="abrir(r)"
              >
                <span class="ico" :data-tono="r.entrada.tono"><Icon :name="r.entrada.icono" :size="16" /></span>
                <span class="txt">
                  <b class="tit"><template v-for="(t, k) in tramos(r.entrada.titulo, r.marcas)" :key="k"><mark v-if="t.on">{{ t.t }}</mark><template v-else>{{ t.t }}</template></template></b>
                  <small v-if="r.entrada.sub">{{ r.entrada.sub }}</small>
                </span>
                <span class="go" aria-hidden="true"><Icon name="arrow-right" :size="14" /></span>
              </button>
            </section>
            <p v-if="!filas.length" class="vacio">
              <Icon name="search" :size="22" />
              <span v-if="q.trim()">Nada coincide con «{{ q.trim() }}»</span>
              <span v-else>Todavía no hay nada para buscar</span>
            </p>
          </div>

          <footer v-if="desktop" class="pal-foot" aria-hidden="true">
            <span><kbd>↑</kbd><kbd>↓</kbd> moverse</span>
            <span><kbd>↵</kbd> abrir</span>
            <span><kbd>Tab</kbd> cambiar de grupo</span>
            <span class="push"><kbd>{{ ATAJO }}</kbd> abrir o cerrar</span>
          </footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.pal {
  position: fixed;
  left: 0;
  right: 0;
  top: 0;
  height: 100dvh;
  z-index: 600;
  display: flex;
  justify-content: center;
  align-items: flex-start;
  --pal-max: 78dvh;
}
.pal-back {
  position: absolute;
  inset: 0;
  background: rgb(6 8 7 / 0.55);
  backdrop-filter: blur(5px);
}
:root[data-theme='light'] .pal-back { background: rgb(30 34 30 / 0.34); }
.pal-panel {
  position: relative;
  width: 100%;
  max-height: var(--pal-max);
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding-top: env(safe-area-inset-top);
  border-radius: 0 0 22px 22px;
  background: var(--surface-2);
  box-shadow: var(--shadow-pop), 0 30px 80px -30px rgb(0 0 0 / 0.6);
  overflow: hidden;
}
.pal.wide { align-items: flex-start; }
.pal.wide .pal-panel {
  width: min(640px, calc(100vw - 32px));
  max-height: min(560px, 72dvh);
  margin-top: 13vh;
  padding-top: 0;
  border-radius: 18px;
}
.pal-in {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px 12px 16px;
  border-bottom: 1px solid var(--line);
  flex: none;
}
.lupa { color: var(--accent); flex: none; }
.pal-input {
  flex: 1;
  min-width: 0;
  height: 36px;
  font: inherit;
  font-size: 16px;
  color: var(--text);
  background: transparent;
  border: 0;
  outline: 0;
}
.pal-input::placeholder { color: var(--text-4); }
.clear {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  color: var(--text-3);
  background: var(--surface-hover);
  transition: color 0.2s, scale 0.3s var(--spring);
}
.clear:active { scale: var(--press-scale); }
.cancel {
  height: 30px;
  padding: 0 4px 0 8px;
  font-size: var(--t-lg);
  font-weight: 540;
  color: var(--accent);
}
kbd {
  display: inline-grid;
  place-items: center;
  min-width: 22px;
  height: 22px;
  padding: 0 6px;
  border-radius: 6px;
  font: 600 11px/1 var(--font-mono);
  color: var(--text-3);
  background: var(--keycap);
  box-shadow: inset 0 0 0 1px var(--keycap-rim), 0 1px 0 var(--keycap-skirt);
}
.pal-list {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 4px 8px calc(10px + env(safe-area-inset-bottom));
  scrollbar-width: thin;
}
.pal.wide .pal-list { padding-bottom: 8px; }
.cursor {
  position: absolute;
  left: 8px;
  right: 8px;
  top: 0;
  height: 0;
  opacity: 0;
  border-radius: 12px;
  background: var(--surface-hover);
  box-shadow: inset 0 0 0 1px var(--accent-line), 0 6px 22px -12px var(--accent);
  pointer-events: none;
}
.grp h3 {
  margin: 0;
  padding: 12px 10px 5px;
  font-size: var(--t-xs);
  font-weight: 650;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-4);
}
.row {
  position: relative;
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 52px;
  padding: 8px 10px;
  border-radius: 12px;
  text-align: left;
  color: var(--text-2);
}
.ico {
  flex: none;
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--r-md);
  color: var(--text-3);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  transition: color 0.25s, background 0.25s, transform 0.4s var(--spring);
}
.ico[data-tono='working'] { color: var(--st-working); background: var(--st-working-soft); }
.ico[data-tono='blocked'] { color: var(--st-blocked); background: var(--st-blocked-soft); }
.ico[data-tono='done'] { color: var(--st-done); background: var(--st-done-soft); }
.row.on .ico { color: var(--accent); transform: scale(1.06); }
.row.on .ico[data-tono='working'] { color: var(--st-working); }
.row.on .ico[data-tono='blocked'] { color: var(--st-blocked); }
.row.on .ico[data-tono='done'] { color: var(--st-done); }
.txt {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 1px;
}
.tit {
  font-weight: 540;
  font-size: 14px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.txt small {
  font-size: 12px;
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
mark {
  color: var(--accent);
  background: transparent;
  font-weight: 700;
}
.go {
  flex: none;
  color: var(--accent);
  opacity: 0;
  transform: translateX(-6px);
  transition: opacity 0.2s, transform 0.35s var(--spring);
}
.row.on .go { opacity: 1; transform: none; }
@media (hover: none) { .go { display: none; } }
.vacio {
  display: grid;
  justify-items: center;
  gap: 10px;
  margin: 0;
  padding: 38px 16px 34px;
  font-size: var(--t-lg);
  color: var(--text-3);
}
.vacio :deep(svg) { color: var(--text-4); }
.pal-foot {
  display: flex;
  gap: 16px;
  align-items: center;
  flex: none;
  padding: 9px 16px;
  border-top: 1px solid var(--line);
  font-size: var(--t-sm);
  color: var(--text-4);
}
.pal-foot span { display: inline-flex; align-items: center; gap: 5px; }
.pal-foot kbd { min-width: 20px; height: 20px; font-size: var(--t-xs); }
.pal-foot .push { margin-left: auto; }
@media (max-width: 1023px) {
  .pal-input { height: 40px; }
  .row { min-height: 56px; }
}
:root[data-motion='soft'] .ico, :root[data-motion='soft'] .go { transition: none; }
</style>
