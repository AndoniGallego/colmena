<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import { resumeCommand, soloUnknown, targetLine, unsafeCwd } from '../lib/cerrar'
import { copyText } from '../lib/clipboard'
import { boardState } from '../state/app'
import { useConfirmacionBoton } from '../lib/confirmacionBoton'
import ListoOverlay from './ListoOverlay.vue'
import { accionLoteSheet, borrarCopia, close, confirmClose, dismissClose, refreshPreview } from '../state/cerrar'
import { gsap, isSoft, useGsap } from '../motion'
import ClosePaneList from './ClosePaneList.vue'
import GuardandoLote from './GuardandoLote.vue'
import Icon from './Icon.vue'
import InlineAlert from './InlineAlert.vue'

const { run } = useGsap()
const panel = ref<HTMLElement | null>(null)
const open = computed(() => !!close.target)
const t = computed(() => close.target)
const tipo = computed(() => t.value?.tipo ?? 'tab')
const label = computed(() => close.preview?.label || t.value?.label || t.value?.targetId || '')
const where = computed(() => (close.preview ? targetLine(close.preview) : ''))
const blockers = computed(() => close.preview?.bloqueantes ?? [])
const busy = computed(() => close.phase === 'closing')
const guardando = computed(() => close.phase === 'guardando' && !!close.lote)
const loading = computed(() => close.phase === 'loading')
const showList = computed(() => !!close.preview && (close.phase === 'ready' || close.phase === 'closing'))

const armed = ref(true)
let armTimer: ReturnType<typeof setTimeout> | undefined
const cancelBtn = ref<HTMLButtonElement | null>(null)
const copyBtn = ref<HTMLButtonElement | null>(null)
const { hecho: copiado, error: copiaErr, fallo: copiaFallo, pulsarHecho: copiaOk } = useConfirmacionBoton()
const { onKeydown } = useFocusTrap(panel, open, {
  onEscape: dismissClose,
  initial: () => cancelBtn.value ?? panel.value,
})
useSheetSwipe(panel, dismissClose)

watch(open, (on) => {
  clearTimeout(armTimer)
  if (!on) return
  armed.value = !(tipo.value === 'workspace' && (t.value?.tabCount ?? 1) > 1)
  if (!armed.value) armTimer = setTimeout(() => (armed.value = true), 1000)
})
onBeforeUnmount(() => clearTimeout(armTimer))

watch(
  () => boardState.value.board,
  () => open.value && refreshPreview(),
)

const primary = computed(() => {
  if (busy.value) return 'Cerrando…'
  if (blockers.value.length) return 'Frenala primero'
  return tipo.value === 'tab' ? 'Cerrar tab' : 'Cerrar workspace'
})
const puedeForzar = computed(() => close.phase === 'ready' && soloUnknown(blockers.value))
const puedeForzarYa = computed(() => puedeForzar.value && armed.value)
const canConfirm = computed(() => close.phase === 'ready' && !blockers.value.length && armed.value)

const manual = computed(() => close.sesiones.filter((x) => unsafeCwd(x) && x.session_id))
const commands = computed(() =>
  close.sesiones.map((s) => ({ titulo: s.titulo, cmd: resumeCommand(s) })).filter((c): c is { titulo: string; cmd: string } => !!c.cmd),
)
async function copy(cmd: string) {
  if (!(await copyText(cmd))) return copiaFallo('No pude copiar el comando', copyBtn.value)
  await copiaOk()
}

const sheetLayout = () => window.matchMedia('(max-width: 639px)').matches

function onEnter(el: Element, done: () => void) {
  const back = el.querySelector('.sheet-scrim')
  const card = el.querySelector('.cs-panel')
  if (isSoft()) {
    run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
    return
  }
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(back, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'power2.out' }, 0)
    if (sheetLayout()) tl.fromTo(card, { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    else tl.fromTo(card, { y: 24, scale: 0.96, opacity: 0 }, { y: 0, scale: 1, opacity: 1, duration: 0.55, ease: 'expo.out' }, 0)
    tl.from(el.querySelectorAll('.cs-stagger > *'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', stagger: 0.05 }, 0.18)
  })
}
function onLeave(el: Element, done: () => void) {
  const card = el.querySelector('.cs-panel')
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
      <div v-if="open" class="sheet-root cs" @keydown="onKeydown">
        <div class="sheet-scrim cs-back" @click="dismissClose" />
        <section
          ref="panel"
          class="sheet-panel cs-panel"
          role="dialog"
          aria-modal="true"
          :aria-labelledby="'cs-title'"
          tabindex="-1"
          :data-phase="close.phase"
        >
          <i class="sheet-grip grip" aria-hidden="true" />

          <template v-if="close.phase === 'done'">
            <div class="sheet-stagger cs-stagger done">
              <span class="done-mark"><Icon name="check" :size="20" /></span>
              <h2 id="cs-title" class="sheet-title title">{{ tipo === 'tab' ? 'Tab cerrado' : 'Workspace cerrado' }}</h2>
              <template v-if="commands.length">
                <p class="note">Las conversaciones de Claude quedaron guardadas. Para retomarlas:</p>
                <div v-for="c in commands" :key="c.cmd" class="cmd">
                  <span v-if="c.titulo" class="cmd-title">{{ c.titulo }}</span>
                  <code>{{ c.cmd }}</code>
                  <button ref="copyBtn" type="button" class="btn btn-ghost btn-sm" :class="{ done: copiado, err: !!copiaErr }" @click="copy(c.cmd)"><Icon name="doc" :size="13" /> {{ copiaErr || (copiado ? 'Copiado' : 'Copiar comando para retomar') }}</button>
                </div>
              </template>
              <p v-for="m in manual" :key="m.session_id!" class="note">
                {{ m.titulo || m.session_id }}: Ruta con caracteres raros: retomala a mano
              </p>
              <div v-for="c in close.copias" :key="c.ruta" class="copia">
                <p class="note">Copia del repo de la tarea: <code>{{ c.ruta }}</code> (rama {{ c.rama }})</p>
                <p v-if="c.estado === 'borrada'" class="note copia-ok">Copia borrada.</p>
                <template v-else-if="c.borrable">
                  <button type="button" class="btn btn-ghost btn-sm" :disabled="c.estado === 'borrando'" :aria-busy="c.estado === 'borrando'" @click="borrarCopia(c.ruta)">
                    {{ c.estado === 'borrando' ? 'Borrando…' : 'Borrar también la copia del repo' }}
                  </button>
                  <p v-if="c.error" class="note copia-err" role="alert">{{ c.error }}</p>
                </template>
                <p v-else class="note">No la borro: {{ c.motivo.charAt(0).toLowerCase() + c.motivo.slice(1) }}.</p>
              </div>
              <div class="sheet-actions actions"><button type="button" class="btn btn-primary" @click="dismissClose">Listo</button></div>
            </div>
          </template>

          <template v-else-if="guardando">
            <div class="sheet-stagger cs-stagger">
              <h2 id="cs-title" class="sheet-title title">Guardando antes de cerrar “{{ label }}”</h2>
              <InlineAlert v-if="close.notice">{{ close.notice }}</InlineAlert>
              <GuardandoLote :lote="close.lote!" @accion="accionLoteSheet" />
              <div class="sheet-actions actions"><button type="button" class="btn btn-ghost" @click="dismissClose">Cerrar esta ventana</button></div>
            </div>
          </template>

          <template v-else-if="close.phase === 'gone' || close.phase === 'error'">
            <div class="sheet-stagger cs-stagger">
              <h2 id="cs-title" class="sheet-title title">{{ close.phase === 'gone' ? 'Ya no está' : `No se puede cerrar ${tipo === 'tab' ? 'el tab' : 'el workspace'}` }}</h2>
              <InlineAlert>{{ close.error }}</InlineAlert>
              <div class="sheet-actions actions"><button type="button" class="btn btn-ghost" @click="dismissClose">Entendido</button></div>
            </div>
          </template>

          <template v-else>
            <div class="sheet-stagger cs-stagger">
              <h2 id="cs-title" class="sheet-title title">¿Cerrar {{ tipo === 'tab' ? 'el tab' : 'el workspace' }} “{{ label }}”?</h2>
              <p v-if="where" class="where mono">{{ where }}</p>
              <InlineAlert v-if="close.notice">{{ close.notice }}</InlineAlert>
              <p v-if="close.preview?.cierra_workspace" class="notice"><Icon name="warn" :size="13" /> Es el único tab: se cierra también el workspace</p>

              <div v-if="loading" class="skeleton" aria-label="Cargando" aria-busy="true"><i /><i /></div>
              <ClosePaneList v-if="showList" :panes="close.preview!.panes" :bloqueantes="blockers" actions />

              <p v-if="showList" class="note">
                Antes de cerrar les pido a las sesiones que guarden en Engram. Las conversaciones de Claude quedan guardadas en disco: las podés retomar con <code>claude --resume</code>. Lo que corre en las terminales se corta.
              </p>

              <div class="sheet-actions actions">
                <button
                  type="button"
                  class="btn btn-danger"
                  :class="{ spinning: busy }"
                  :disabled="!canConfirm"
                  :aria-busy="busy"
                  @click="confirmClose()"
                >
                  <span v-if="busy" class="spin" aria-hidden="true" />{{ primary }}
                </button>
                <button v-if="puedeForzar && !busy" type="button" class="btn btn-danger" :disabled="!puedeForzarYa" @click="confirmClose(false, true)">Cerrar igual</button>
                <button v-if="showList && !busy" type="button" class="btn btn-ghost" :disabled="!canConfirm" @click="confirmClose(true)">Cerrar sin guardar</button>
                <button ref="cancelBtn" type="button" class="btn btn-ghost" :disabled="busy" @click="dismissClose">Cancelar</button>
              </div>
            </div>
          </template>
          <ListoOverlay :visible="!!close.listoTxt && close.phase === 'done'" :texto="close.listoTxt" />
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.cs {
  z-index: 50;
}
.cs-panel {
  outline: none;
}
.where {
  margin: -4px 0 0;
  font-size: 12px;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.note {
  margin: 0;
  font-size: var(--t-md);
  line-height: 1.5;
  color: var(--text-3);
}
.note code,
.cmd code {
  font-family: var(--font-mono);
  font-size: 12px;
}
.notice {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0;
  padding: 8px 11px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
}
.skeleton {
  display: grid;
  gap: 6px;
}
.skeleton i {
  height: 40px;
  border-radius: var(--r-md);
  background: linear-gradient(90deg, var(--bg-2), var(--surface-hover), var(--bg-2)) 0 0 / 200% 100%;
  animation: ui-shimmer 1.2s linear infinite;
}
.btn-danger:disabled {
  background: var(--surface-2);
  color: var(--text-4);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.btn-danger.spinning:disabled {
  background: var(--danger);
  color: var(--danger-ink);
  box-shadow: none;
  opacity: 0.85;
}
.done {
  justify-items: stretch;
}
.done-mark {
  display: inline-grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 50%;
  color: var(--st-done);
  background: var(--st-done-soft);
}
.cmd {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border-radius: var(--r-md);
  background: var(--bg-2);
  border: 1px solid var(--line);
}
.cmd-title {
  font-size: var(--t-md);
  color: var(--text-2);
}
.cmd code {
  color: var(--text);
  overflow-wrap: anywhere;
  user-select: all;
}
:root[data-motion='soft'] .skeleton i {
  animation: none;
}
</style>
