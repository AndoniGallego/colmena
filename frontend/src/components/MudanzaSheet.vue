<script setup lang="ts">
import { computed, ref } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { gsap, isSoft, useGsap } from '../motion'
import { cerrarMudanza, confirmarMudanza, mz, quietas } from '../state/mudanza'
import Icon from './Icon.vue'
import ListoOverlay from './ListoOverlay.vue'

const { run } = useGsap()
const panel = ref<HTMLElement | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)
const { onKeydown } = useFocusTrap(panel, () => mz.open, {
  onEscape: () => {
    if (!mz.ocupado) cerrarMudanza()
  },
  initial: () => cancelBtn.value,
})

const titulo = computed(() => {
  if (mz.resultado) return 'Resumen'
  return mz.modo === 'una' ? 'Pasar a tu terminal propia' : 'Mudar todas las quietas'
})

const nQuietas = computed(() => quietas.value.length)

const nombresLista = computed(() => {
  const n = quietas.value.map((s) => s.nombre)
  if (n.length <= 6) return n
  return [...n.slice(0, 6), `y ${n.length - 6} más`]
})

const confirmLabel = computed(() => (mz.modo === 'una' ? 'Pasar' : `Mudar ${nQuietas.value}`))
const busyLabel = computed(() => (mz.modo === 'una' ? 'Pasando…' : 'Mudando…'))

function enter(node: Element, done: () => void) {
  if (isSoft()) return done()
  run(() =>
    gsap.fromTo(node, { y: 36, opacity: 0 }, { y: 0, opacity: 1, duration: 0.45, ease: 'power3.out', clearProps: 'transform,opacity', onComplete: done }),
  )
}

function leave(node: Element, done: () => void) {
  if (isSoft()) return done()
  run(() => gsap.to(node, { y: 24, opacity: 0, duration: 0.25, ease: 'power2.in', onComplete: done }))
}

const nombreDe = (pane: string) => mz.sesiones.find((c) => c.pane_id === pane)?.nombre || pane

function listo() {
  cerrarMudanza()
}
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="enter" @leave="leave">
      <div v-if="mz.open" class="sheet-root qs-bg" @keydown="onKeydown">
        <div class="sheet-scrim" @click="!mz.ocupado && cerrarMudanza()" />
        <div ref="panel" class="sheet-panel qs mz-wrap" role="alertdialog" aria-modal="true" aria-labelledby="mz-t" aria-describedby="mz-d">
          <span class="qs-ic"><Icon name="terminal" :size="20" /></span>
          <h3 id="mz-t" class="sheet-title">{{ titulo }}</h3>

          <template v-if="mz.resultado">
            <div id="mz-d" class="resumen">
              <p v-if="mz.resultado.mudadas.length">Pasaron {{ mz.resultado.mudadas.length }}.</p>
              <p v-else>Ninguna pasó en esta tanda.</p>
              <ul v-if="mz.resultado.saltadas.length" class="det">
                <li v-for="s in mz.resultado.saltadas" :key="s.pane_id"><b>{{ nombreDe(s.pane_id) }}</b>: {{ s.motivo }}</li>
              </ul>
              <ul v-if="mz.resultado.fallidas.length" class="det fail">
                <li v-for="f in mz.resultado.fallidas" :key="f.pane_id"><b>{{ nombreDe(f.pane_id) }}</b>: {{ f.motivo }}</li>
              </ul>
            </div>
            <div class="sheet-actions qs-actions">
              <button type="button" class="btn btn-primary btn-block" @click="listo">Listo</button>
            </div>
          </template>

          <template v-else>
            <p v-if="mz.modo === 'una'" id="mz-d">
              Se cierra en Herdr y sigue en tu terminal propia, con todo el historial.
              <span v-if="mz.objetivo" class="sub">«{{ mz.objetivo.nombre }}» · {{ mz.objetivo.workspace }}</span>
            </p>
            <div v-else id="mz-d">
              <p>
                Se cierran en Herdr y siguen en tu terminal propia, con todo el historial. Las que estén trabajando no se tocan.
              </p>
              <ul v-if="nombresLista.length" class="nombres">
                <li v-for="(n, i) in nombresLista" :key="i">{{ n }}</li>
              </ul>
            </div>
            <p v-if="mz.error" class="warn">{{ mz.error }}</p>
            <div class="sheet-actions qs-actions">
              <button ref="cancelBtn" type="button" class="btn btn-ghost" :disabled="mz.ocupado" @click="cerrarMudanza()">Cancelar</button>
              <button type="button" class="btn btn-primary" :disabled="mz.ocupado" @click="confirmarMudanza()">
                <Icon name="terminal" :size="14" /> {{ mz.ocupado ? busyLabel : confirmLabel }}
              </button>
            </div>
          </template>
          <ListoOverlay :visible="mz.listo" :texto="mz.listoTxt" />
        </div>
        <p v-if="mz.bloqueoMsg" class="bloqueo-msg" role="alert">{{ mz.bloqueoMsg }}</p>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.qs-bg {
  z-index: 90;
}
.mz-wrap {
  position: relative;
}
.qs {
  width: 100%;
  box-sizing: border-box;
  display: grid;
  justify-items: start;
  gap: 10px;
}
.bloqueo-msg {
  position: absolute;
  left: 50%;
  bottom: 24px;
  transform: translateX(-50%);
  margin: 0;
  max-width: calc(100vw - 32px);
  padding: 8px 14px;
  border-radius: var(--r-md);
  font-size: 13px;
  color: var(--danger);
  background: var(--danger-soft);
  border: 1px solid color-mix(in srgb, var(--danger) 40%, transparent);
}
.qs-ic {
  display: grid;
  place-items: center;
  width: 42px;
  height: 42px;
  border-radius: var(--r-lg);
  color: var(--accent);
  background: var(--accent-soft);
}
p {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
.sub {
  display: block;
  margin-top: 8px;
  font-size: var(--t-md);
  color: var(--text-3, var(--text-2));
}
.nombres {
  margin: 8px 0 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-2);
}
.resumen p {
  margin: 0 0 6px;
}
.det {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 13px;
  color: var(--text-2);
}
.det.fail {
  color: var(--st-blocked);
}
.warn {
  color: var(--st-blocked);
  font-size: 13px;
}
.qs-actions {
  justify-self: stretch;
  margin-top: 8px;
}
@media (min-width: 720px) {
  .qs {
    width: 400px;
  }
  .qs-actions {
    justify-content: flex-end;
  }
}
</style>
