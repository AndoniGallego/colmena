<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { boardState, jumpTo, revokeAllSessions } from '../state/app'
import { lib, libVisible } from '../state/biblioteca'
import { piezas } from '../piezas'
import { mrs, mrsVisible, pendientesMrs } from '../state/mrs'
import { notasVisible, pendientes as notasPendientes } from '../state/notas'
import { abrirLimpieza as abrirLimpiezaSesiones } from '../state/limpieza'
import { desktop } from '../lib/viewport'
import type { AttentionKind } from '../lib/order'
import { summarize } from '../state/boardReducer'
import { clock, useNow } from '../lib/time'
import { setTheme, theme } from '../lib/theme'
import { openAjustes } from '../state/ajustes'
import { openEntornos } from '../state/entornos'
import { openKit } from '../state/kit'
import { openTareas } from '../state/tareas'
import { abrirPaleta } from '../state/buscador'
import { ATAJO } from '../lib/buscador'
import BrandLockup from './BrandLockup.vue'
import SinConexion from './SinConexion.vue'
import Icon from './Icon.vue'
import NavMark from './NavMark.vue'
import AvisosBell from './AvisosBell.vue'
import UsoPlanPill from './UsoPlanPill.vue'
import RollingNumber from './RollingNumber.vue'
import { gsap, isSoft, ring, useGsap } from '../motion'
import { useFocusTrap } from '../lib/focusTrap'
import { useTopBarMenu } from './useTopBarMenu'

const seccionesPieza = piezas().flatMap((p) => (p.seccion ? [{ id: p.id, ...p.seccion }] : []))
const piezaVisible = computed(() => seccionesPieza.some((s) => s.visible.value))
function apagarPiezas(salvo = '') {
  for (const s of seccionesPieza) if (s.id !== salvo) s.visible.value = false
}

defineProps<{ compact?: boolean }>()

const now = useNow()
const summary = computed(() => summarize(boardState.value.board))
const chips = computed(() => {
  const s = summary.value
  const all: { kind: AttentionKind; n: number; icon: 'warn' | 'ask' | 'chat' | 'pulse'; one: string; many: string }[] = [
    { kind: 'blocked', n: s.blocked, icon: 'warn', one: 'bloqueado', many: 'bloqueados' },
    { kind: 'asks', n: s.asks, icon: 'ask', one: 'te pregunta', many: 'te preguntan' },
    { kind: 'unread', n: s.unread, icon: 'chat', one: 'respuesta nueva', many: 'respuestas nuevas' },
    { kind: 'working', n: s.working, icon: 'pulse', one: 'trabajando', many: 'trabajando' },
  ]
  return all.filter((c) => c.n > 0).map((c) => ({ ...c, label: c.n === 1 ? c.one : c.many }))
})
const calmLabel = computed(() => (summary.value.total ? 'Todo en calma' : 'Sin sesiones'))
const conn = computed(() => boardState.value.connection)
const connLabel = computed(() => ({ live: 'En vivo', connecting: 'Conectando', reconnecting: 'Reconectando' })[conn.value])

const { run } = useGsap()
const bar = ref<HTMLElement | null>(null)

function toggleTheme(e: MouseEvent) {
  setTheme(theme.value === 'dark' ? 'light' : 'dark', e.currentTarget as HTMLElement)
}

const {
  menuOpen,
  menuConfirming: confirming,
  revoking,
  menuEl,
  menuPop,
  menuPos,
  salirPopOpen,
  salirBtnRef,
  salirPopRef,
  salirPos,
  toggleMenu,
  toggleSalirPopover,
  onDoc,
  onKey,
  revoke,
  closeAllOverlays,
} = useTopBarMenu(revokeAllSessions)
/** refs usados en plantilla (vue-tsc no marca uso vía ref="") */
void menuEl
void salirBtnRef
void salirPopRef
const salirCancelBtn = ref<HTMLButtonElement | null>(null)
const { onKeydown: salirTrapKeydown } = useFocusTrap(salirPopRef, salirPopOpen, {
  onEscape: () => {
    salirPopOpen.value = false
  },
  initial: () => salirCancelBtn.value,
})
const chipEls = new Map<string, HTMLElement>()
const chipRef = (kind: string) => (el: unknown) => {
  if (el instanceof HTMLElement) chipEls.set(kind, el)
  else chipEls.delete(kind)
}
watch(
  () => chips.value.map((c) => `${c.kind}:${c.n}`).join(),
  async (_n, o) => {
    if (!o || isSoft()) return
    const before = Object.fromEntries(o.split(',').filter(Boolean).map((x) => x.split(':')))
    await nextTick()
    for (const c of chips.value) {
      const was = Number(before[c.kind] ?? 0)
      const el = chipEls.get(c.kind)
      if (!el || !was || c.n === was) continue
      run(() => gsap.fromTo(el, { scale: c.n > was ? 1.16 : 0.9 }, { scale: 1, duration: 0.7, ease: 'elastic.out(1.1, 0.45)' }))
      if (c.n > was && c.kind !== 'working') ring(el, getComputedStyle(el).color, 44)
    }
  },
)

watch(menuOpen, async (o) => {
  if (!o || isSoft()) return
  await nextTick()
  const items = menuPop.value?.querySelectorAll(':scope > *')
  if (items?.length) run(() => gsap.from(items, { y: -6, opacity: 0, duration: 0.4, ease: 'power3.out', stagger: 0.05, delay: 0.05 }))
})

onMounted(() => {
  if (bar.value && !isSoft()) {
    const q = gsap.utils.selector(bar.value)
    run(() =>
      gsap.from([...q('.brand'), ...q('.readout'), ...q('.right > *')], {
        y: -10,
        opacity: 0,
        duration: 0.7,
        ease: 'expo.out',
        stagger: 0.05,
        delay: 0.1,
        clearProps: 'transform,opacity',
      }),
    )
  }
  document.addEventListener('pointerdown', onDoc)
  document.addEventListener('keydown', onKey)
  window.addEventListener('resize', closeAllOverlays)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDoc)
  document.removeEventListener('keydown', onKey)
  window.removeEventListener('resize', closeAllOverlays)
})
</script>

<template>
  <header ref="bar" class="bar" :class="{ compact }">
    <div class="brand">
      <BrandLockup :size="26" :live="conn === 'live'" :working="summary.working > 0" :active="summary.working" :attention="summary.blocked + summary.asks > 0" />
    </div>

    <nav v-if="!compact" class="sections" aria-label="Secciones">
      <button class="sec" title="Tablero" :class="{ on: !libVisible && !piezaVisible && !mrsVisible && !notasVisible }" :aria-current="!libVisible && !piezaVisible && !mrsVisible && !notasVisible ? 'page' : undefined" @click="libVisible = mrsVisible = notasVisible = false; apagarPiezas()">
        <NavMark name="board" :size="15" :active="!libVisible && !piezaVisible && !mrsVisible && !notasVisible" /> <span class="sec-lbl">Tablero</span>
      </button>
      <button v-if="mrs.habilitado" class="sec" title="Merge requests" :class="{ on: mrsVisible }" :aria-current="mrsVisible ? 'page' : undefined" @click="libVisible = notasVisible = false; apagarPiezas(); mrsVisible = true">
        <NavMark name="merge" :size="15" :active="mrsVisible" /> <span class="sec-lbl">MRs</span>
        <i v-if="pendientesMrs && !mrsVisible" class="sec-dot" role="img" aria-label="Hay MRs que piden atención" />
      </button>
      <button
        v-for="sp in seccionesPieza"
        :key="sp.id"
        class="sec"
        :title="sp.titulo"
        :class="{ on: sp.visible.value }"
        :aria-current="sp.visible.value ? 'page' : undefined"
        @click="libVisible = mrsVisible = notasVisible = false; apagarPiezas(sp.id); sp.visible.value = true"
      >
        <NavMark :name="sp.icono" :size="15" :active="sp.visible.value" /> <span class="sec-lbl">{{ sp.titulo }}</span>
      </button>
      <button
        class="sec"
        title="Notas"
        data-notas-destino
        :class="{ on: notasVisible }"
        :aria-current="notasVisible ? 'page' : undefined"
        :aria-label="notasPendientes ? `Notas, ${notasPendientes} para hacer` : undefined"
        @click="libVisible = mrsVisible = false; apagarPiezas(); notasVisible = true"
      >
        <Icon name="hex" :size="15" /> <span class="sec-lbl">Notas</span>
        <b v-if="notasPendientes" class="sec-miel mono">{{ notasPendientes }}</b>
      </button>
      <button class="sec" title="Biblioteca" :class="{ on: libVisible }" :aria-current="libVisible ? 'page' : undefined" @click="mrsVisible = notasVisible = false; apagarPiezas(); libVisible = true">
        <NavMark name="library" :size="15" :active="libVisible" /> <span class="sec-lbl">Biblioteca</span>
        <i v-if="lib.newCount && !libVisible" class="sec-dot" role="img" aria-label="Hay novedades" />
      </button>
    </nav>

    <div class="readout" role="group" aria-label="Resumen">
      <TransitionGroup name="chipx">
        <button
          v-for="c in chips"
          :key="c.kind"
          :ref="chipRef(c.kind)"
          class="stat hit"
          :data-st="c.kind"
          :title="`${c.n} ${c.label}: ir a la primera`"
          :aria-label="`${c.n} ${c.label}: ir a la primera`"
          @click="jumpTo(c.kind)"
        >
          <Icon :name="c.icon" :size="13" />
          <b class="mono"><RollingNumber :value="c.n" /></b>
          <span class="lbl">{{ c.label }}</span>
        </button>
      </TransitionGroup>
      <span v-if="!chips.length" class="calm">{{ calmLabel }}</span>
    </div>

    <div class="right">
      <UsoPlanPill :compact="compact" />
      <span class="conn" :data-conn="conn" :title="connLabel">
        <i />
        <span class="conn-lbl">{{ connLabel }}</span>
      </span>
      <span class="clock mono">{{ clock(now) }}</span>
      <button v-if="!compact" class="search" aria-label="Buscar" aria-keyshortcuts="Control+K Meta+K" @click="abrirPaleta">
        <Icon name="search" :size="14" />
        <span>Buscar</span>
        <kbd>{{ ATAJO }}</kbd>
      </button>
      <button v-else class="icon-btn hit" aria-label="Buscar" @click="abrirPaleta"><Icon name="search" :size="16" /></button>
      <AvisosBell />
      <button class="icon-btn hit" :aria-label="theme === 'dark' ? 'Tema claro' : 'Tema oscuro'" @click="toggleTheme($event)">
        <Transition name="icon-swap" mode="out-in">
          <Icon :key="theme" :name="theme === 'dark' ? 'sun' : 'moon'" :size="16" />
        </Transition>
      </button>
      <template v-if="!compact && desktop">
        <button type="button" class="icon-btn hit" aria-label="Ajustes" title="Ajustes" @click="openAjustes">
          <Icon name="grid" :size="16" />
        </button>
        <button type="button" class="icon-btn hit" aria-label="Entornos" title="Entornos: tiendas y servicios de la notebook" @click="openEntornos">
          <Icon name="monitor" :size="16" />
        </button>
        <button type="button" class="icon-btn hit" aria-label="Kit" title="Kit: reglas, skills y hooks de Claude" @click="openKit">
          <Icon name="hex" :size="16" />
        </button>
        <button type="button" class="icon-btn hit" aria-label="Tareas programadas" title="Tareas programadas" @click="openTareas">
          <Icon name="clock" :size="16" />
        </button>
        <button type="button" class="icon-btn hit" aria-label="Limpiar sesiones" title="Limpiar sesiones" @click="abrirLimpiezaSesiones()">
          <Icon name="broom" :size="16" />
        </button>
        <div ref="salirBtnRef" class="menu-wrap salir-wrap">
          <button type="button" class="icon-btn hit" aria-label="Salir de Colmena" title="Salir de Colmena" @click="toggleSalirPopover">
            <Icon name="power" :size="16" />
          </button>
          <Teleport to="body">
            <Transition name="pop">
              <div v-if="salirPopOpen" ref="salirPopRef" class="menu salir-pop" role="dialog" aria-modal="true" aria-label="Confirmar salida" :style="{ top: `${salirPos.top}px`, right: `${salirPos.right}px` }" @keydown="salirTrapKeydown">
                <div class="confirm">
                  <p>Salís de Colmena en todos tus dispositivos, este incluido, y vas a tener que poner el PIN de nuevo. Las terminales y las sesiones de Claude no se tocan.</p>
                  <div class="confirm-actions">
                    <button ref="salirCancelBtn" type="button" class="c-btn" :disabled="revoking" @click="salirPopOpen = false">Cancelar</button>
                    <button type="button" class="c-btn danger" :disabled="revoking" @click="revoke">{{ revoking ? 'Saliendo…' : 'Salir' }}</button>
                  </div>
                </div>
              </div>
            </Transition>
          </Teleport>
        </div>
      </template>
      <div v-else ref="menuEl" class="menu-wrap">
        <button class="icon-btn hit" aria-label="Más opciones" aria-haspopup="menu" :aria-expanded="menuOpen" @click="toggleMenu">
          <Icon name="dots" :size="16" />
        </button>
        <Teleport to="body">
        <Transition name="pop">
          <div v-if="menuOpen" ref="menuPop" class="menu" role="menu" :style="{ top: `${menuPos.top}px`, right: `${menuPos.right}px` }">
            <button v-if="!confirming" class="item" role="menuitem" @click="menuOpen = false; openAjustes()">
              <Icon name="grid" :size="14" />
              <span class="item-txt">Ajustes<small>Apariencia, avisos, permisos</small></span>
            </button>
            <button v-if="!confirming" class="item" role="menuitem" @click="menuOpen = false; openEntornos()">
              <Icon name="monitor" :size="14" />
              <span class="item-txt">Entornos<small>Tiendas y servicios de la notebook</small></span>
            </button>
            <button v-if="!confirming" class="item" role="menuitem" @click="menuOpen = false; openKit()">
              <Icon name="hex" :size="14" />
              <span class="item-txt">Kit<small>Reglas, skills y hooks de Claude</small></span>
            </button>
            <button v-if="!confirming" class="item" role="menuitem" @click="menuOpen = false; openTareas()">
              <Icon name="clock" :size="14" />
              <span class="item-txt">Tareas programadas<small>Pedidos que corren solos a su hora</small></span>
            </button>
            <button v-if="!confirming && desktop" class="item" role="menuitem" @click="menuOpen = false; abrirLimpiezaSesiones()">
              <Icon name="broom" :size="14" />
              <span class="item-txt">Limpiar sesiones…<small>Cierra las que están quietas</small></span>
            </button>
            <button v-if="!confirming" class="item" role="menuitem" @click="confirming = true">
              <Icon name="power" :size="14" />
              <span class="item-txt">Salir de Colmena<small>En todos tus dispositivos</small></span>
            </button>
            <div v-else class="confirm">
              <p>Salís de Colmena en todos tus dispositivos, este incluido, y vas a tener que poner el PIN de nuevo. Las terminales y las sesiones de Claude no se tocan.</p>
              <div class="confirm-actions">
                <button class="c-btn" :disabled="revoking" @click="confirming = false">Cancelar</button>
                <button class="c-btn danger" :disabled="revoking" @click="revoke">{{ revoking ? 'Saliendo…' : 'Salir' }}</button>
              </div>
            </div>
          </div>
        </Transition>
        </Teleport>
      </div>
    </div>
  </header>
  <SinConexion v-if="compact" />
</template>

<style scoped>
.bar {
  display: flex;
  align-items: center;
  gap: 18px;
  padding: 12px 20px;
  padding-top: max(12px, env(safe-area-inset-top));
  padding-left: max(20px, env(safe-area-inset-left));
  padding-right: max(20px, env(safe-area-inset-right));
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--bg) 80%, transparent);
  backdrop-filter: blur(10px);
  position: relative;
  z-index: 5;
}
.brand {
  display: flex;
  align-items: center;
  --mark-cut: var(--bg);
}
.sections {
  display: flex;
  gap: 2px;
  margin-left: 6px;
  padding: 3px;
  border-radius: var(--r-pill);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
.sec {
  position: relative;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 28px;
  padding: 0 12px 0 10px;
  border-radius: var(--r-pill);
  font-size: var(--t-md);
  font-weight: 540;
  color: var(--text-3);
  transition: color 0.25s, background 0.3s, scale 0.3s var(--spring);
}
.sec:hover {
  color: var(--text);
}
.sec.on {
  color: var(--text);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.sec.on :deep(svg) {
  color: var(--accent);
}
.sec:active {
  scale: var(--press-scale);
}
.sec-lbl {
  display: inline-block;
  max-width: 90px;
  overflow: hidden;
  white-space: nowrap;
  transition: max-width 0.45s var(--spring), opacity 0.3s;
}
/* Con cinco secciones no entran todas las etiquetas junto al readout: las inactivas quedan solo con el ícono. */
@media (max-width: 1919px) {
  .sec:not(.on) { padding: 0 9px; gap: 0; }
  .sec:not(.on) .sec-lbl { max-width: 0; opacity: 0; }
}
:root[data-motion='soft'] .sec-lbl { transition: none; }
.sec-miel {
  min-width: 17px;
  height: 17px;
  padding: 0 4px;
  border-radius: var(--r-pill);
  display: grid;
  place-items: center;
  margin-left: 2px;
  font-size: var(--t-2xs);
  font-weight: 700;
  line-height: 1;
  background: var(--miel);
  color: var(--bg);
}
.sec-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent);
}
.readout {
  display: flex;
  gap: 6px;
  margin-left: 14px;
  padding-left: 18px;
  border-left: 1px solid var(--line);
  position: relative;
  align-items: center;
}
.stat {
  display: inline-flex;
  flex: none;
  align-items: center;
  gap: 5px;
  white-space: nowrap;
  height: 28px;
  padding: 0 10px 0 8px;
  border-radius: var(--r-pill);
  font-size: var(--t-md);
  color: var(--c);
  background: var(--bg-soft);
  transition: scale 0.3s var(--spring), background 0.2s, opacity 0.3s, box-shadow 0.3s;
}
.stat[data-st='working'] { --c: var(--st-working); --bg-soft: var(--st-working-soft); }
.stat[data-st='unread'] { --c: var(--accent); --bg-soft: var(--accent-soft); }
.stat[data-st='blocked'],
.stat[data-st='asks'] { --c: var(--st-blocked); --bg-soft: var(--st-blocked-soft); }
.stat:hover {
  background: color-mix(in srgb, var(--c) 22%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--c) 35%, transparent), 0 4px 18px -6px var(--c);
}
.stat:active { scale: var(--press-scale); }
.stat[data-st='blocked'] :deep(svg),
.stat[data-st='asks'] :deep(svg) {
  animation: nudge 4.2s var(--ease-in-out) infinite;
  transform-origin: 50% 80%;
}
@keyframes nudge {
  0%, 82%, 100% { transform: rotate(0); }
  86% { transform: rotate(-14deg); }
  90% { transform: rotate(11deg); }
  94% { transform: rotate(-6deg); }
}
.stat b {
  font-weight: 650;
  font-size: var(--t-md);
}
.stat[data-st='working'] :deep(svg) { animation: pulse-dot 1.8s var(--ease-in-out) infinite; }
.lbl { color: var(--c); font-weight: 520; }
.calm {
  font-size: var(--t-md);
  color: var(--text-4);
  padding: 0 4px;
  white-space: nowrap;
}
.chipx-enter-active { transition: transform 0.5s var(--spring), opacity 0.25s; }
.chipx-leave-active { transition: transform 0.2s, opacity 0.2s; position: absolute; }
.chipx-enter-from, .chipx-leave-to { opacity: 0; transform: scale(0.6); }

.right {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 14px;
}
.conn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-3);
}
.conn i {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--st-blocked);
  transition: background 0.4s;
}
.conn[data-conn='live'] i {
  background: var(--st-done);
  box-shadow: 0 0 0 0 var(--st-done-soft);
  animation: ring 2.4s var(--ease-out) infinite;
}
.conn[data-conn='reconnecting'] i,
.conn[data-conn='connecting'] i {
  animation: blink 1s steps(2, jump-none) infinite;
}
.clock {
  font-size: var(--t-md);
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}
.icon-btn {
  width: 32px;
  height: 32px;
  display: grid;
  place-items: center;
  border-radius: var(--r-md);
  color: var(--text-2);
  border: 1px solid var(--line);
  transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), border-color 0.2s;
}
.icon-btn:hover {
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--line-2);
}
.icon-btn:active {
  scale: var(--press-scale);
}
.search {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 32px;
  padding: 0 6px 0 11px;
  border-radius: var(--r-md);
  border: 1px solid var(--line);
  font-size: var(--t-md);
  color: var(--text-3);
  transition: background 0.2s, color 0.2s, border-color 0.2s, scale 0.3s var(--spring);
}
.search:hover {
  background: var(--surface-hover);
  color: var(--text);
  border-color: var(--line-2);
}
.search:active { scale: var(--press-scale); }
.search kbd {
  height: 20px;
  padding: 0 6px;
  display: inline-grid;
  place-items: center;
  border-radius: 6px;
  font: 600 10.5px/1 var(--font-mono);
  color: var(--text-3);
  background: var(--keycap);
  box-shadow: inset 0 0 0 1px var(--keycap-rim);
}
.menu-wrap {
  position: relative;
}
.menu {
  position: fixed;
  width: 262px;
  padding: 6px;
  border-radius: 12px;
  background: var(--surface-2);
  box-shadow: var(--shadow-pop);
  transform-origin: top right;
  z-index: 500;
}
.item {
  display: flex;
  align-items: center;
  gap: 9px;
  width: 100%;
  padding: 9px 10px;
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-2);
  text-align: left;
  transition: background 0.2s, color 0.2s;
}
.item:hover {
  background: var(--surface-hover);
  color: var(--text);
}
.confirm {
  padding: 6px 6px 4px;
}
.item-txt {
  display: grid;
  gap: 1px;
}
.item-txt small {
  font-size: var(--t-sm);
  color: var(--text-4);
}
.confirm p {
  margin: 0 0 10px;
  font-size: var(--t-md);
  line-height: 1.45;
  color: var(--text-2);
}
.confirm-actions {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
}
.c-btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 8px;
  font-size: var(--t-md);
  font-weight: 540;
  color: var(--text-2);
  transition: background 0.2s, scale 0.3s var(--spring), opacity 0.2s;
}
.c-btn:hover {
  background: var(--surface-hover);
}
.c-btn:active {
  scale: var(--press-scale);
}
.c-btn:disabled {
  opacity: 0.5;
  pointer-events: none;
}
.c-btn.danger {
  background: color-mix(in srgb, var(--danger) 16%, transparent);
  color: var(--danger);
}
.c-btn.danger:hover {
  background: color-mix(in srgb, var(--danger) 26%, transparent);
}
.pop-enter-active { transition: opacity 0.2s, transform 0.45s var(--spring); }
.pop-leave-active { transition: opacity 0.12s, transform 0.12s; }
.pop-enter-from,
.pop-leave-to { opacity: 0; transform: scale(0.92) translateY(-4px); }
@media (max-width: 1023px) {
  .right { gap: 10px; }
}

@keyframes pulse-dot {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.45; transform: scale(0.75); }
}
@keyframes ring {
  0% { box-shadow: 0 0 0 0 var(--st-done); }
  70%, 100% { box-shadow: 0 0 0 6px transparent; }
}
@keyframes blink {
  50% { opacity: 0.25; }
}

.compact {
  padding: 10px 12px;
  padding-top: max(10px, env(safe-area-inset-top));
  gap: 8px;
}
.compact .right { gap: 4px; }
.compact .right .icon-btn,
.compact .right :deep(.bell) { width: 30px; }
.compact .readout {
  margin-left: 0;
  padding-left: 10px;
  gap: 5px;
  min-width: 0;
}
.compact .lbl,
.compact .conn-lbl,
.compact .clock {
  display: none;
}
.compact .stat {
  padding: 0 9px 0 7px;
  gap: 4px;
}
.compact .conn[data-conn='live'] i { animation: none; }
@media (max-width: 440px) {
  .compact .brand :deep(.word) { display: none; }
  .compact .readout { border-left: 0; padding-left: 2px; gap: 4px; overflow: hidden; }
  .compact .stat { padding: 0 6px 0 5px; gap: 3px; }
  /* Con la pastilla del plan, a 390px la barra medía 420: se compacta el resto. El punto de conexión sobra:
     SinConexion avisa con una franja cuando se cae. */
  .compact { gap: 6px; }
  .compact .right { gap: 2px; }
  .compact .right .icon-btn,
  .compact .right :deep(.bell) { width: 28px; }
  .compact .conn { display: none; }
}
@media (pointer: coarse) {
  .stat { min-height: 44px; }
}
</style>
