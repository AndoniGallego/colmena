<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { gsap, isSoft, useGsap } from '../motion'
import type { Ancho } from '../lib/divisor'

const props = withDefaults(
  defineProps<{
    ancho: Ancho
    label: string
    /** Lado del divisor donde está el panel que se redimensiona. */
    lado?: 'izq' | 'der'
  }>(),
  { lado: 'izq' },
)

const { run } = useGsap()
const el = ref<HTMLElement | null>(null)
const arrastrando = ref(false)
const sentido = () => (props.lado === 'izq' ? 1 : -1)
const ROOT_CLASS = 'orq-redimensionando'

let drag: { id: number; x0: number; w0: number; movio: boolean } | null = null
let tween: gsap.core.Tween | null = null
let ro: ResizeObserver | null = null

/** Solo cuenta lo visible: si algo empuja el contenedor más allá de la ventana, el otro panel igual tiene que entrar. */
function medir() {
  const host = el.value?.parentElement
  if (!host) return
  const visible = document.documentElement.clientWidth - host.getBoundingClientRect().left
  props.ancho.contenedor.value = Math.min(host.clientWidth, visible)
}

function soltarRaiz() {
  document.documentElement.classList.remove(ROOT_CLASS)
}

function onDown(e: PointerEvent) {
  if (e.button !== 0 || !el.value) return
  e.preventDefault()
  tween?.kill()
  el.value.setPointerCapture(e.pointerId)
  drag = { id: e.pointerId, x0: e.clientX, w0: props.ancho.ancho.value, movio: false }
  arrastrando.value = true
  document.documentElement.classList.add(ROOT_CLASS)
}
function onMove(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return
  const dx = e.clientX - drag.x0
  if (!drag.movio && Math.abs(dx) < 2) return
  drag.movio = true
  props.ancho.ver(drag.w0 + dx * sentido())
}
function onEnd(e: PointerEvent) {
  if (!drag || e.pointerId !== drag.id) return
  const movio = drag.movio
  drag = null
  arrastrando.value = false
  soltarRaiz()
  if (el.value?.hasPointerCapture(e.pointerId)) el.value.releasePointerCapture(e.pointerId)
  if (movio) props.ancho.fijar()
}

function onKey(e: KeyboardEvent) {
  if (props.ancho.teclado(e.key, sentido())) e.preventDefault()
}

function restablecer() {
  tween?.kill()
  const desde = props.ancho.ancho.value
  const hasta = props.ancho.porDefecto.value
  if (desde === hasta) return props.ancho.restablecer()
  const soft = isSoft()
  const p = { v: desde }
  tween = run(() =>
    gsap.to(p, {
      v: hasta,
      duration: soft ? 0.16 : 0.55,
      ease: soft ? 'power2.out' : 'orq.spring',
      onUpdate: () => props.ancho.ver(p.v),
      onComplete: () => {
        tween = null
        props.ancho.restablecer()
      },
    }),
  )
}

onMounted(() => {
  medir()
  const host = el.value?.parentElement
  if (host) {
    ro = new ResizeObserver(medir)
    ro.observe(host)
  }
  window.addEventListener('resize', medir)
})
onBeforeUnmount(() => {
  ro?.disconnect()
  window.removeEventListener('resize', medir)
  tween?.kill()
  soltarRaiz()
})
</script>

<template>
  <div
    ref="el"
    class="divisor"
    :class="{ arrastrando, der: lado === 'der' }"
    :style="lado === 'izq' ? { left: `${ancho.ancho.value}px` } : { right: `${ancho.ancho.value}px` }"
    role="separator"
    aria-orientation="vertical"
    :aria-label="label"
    :aria-valuenow="ancho.ancho.value"
    :aria-valuemin="ancho.limites.value.min"
    :aria-valuemax="ancho.limites.value.max"
    :aria-valuetext="`${ancho.ancho.value} píxeles`"
    title="Arrastrá para cambiar el ancho · doble click vuelve al original"
    tabindex="0"
    @pointerdown.stop="onDown"
    @pointermove="onMove"
    @pointerup="onEnd"
    @pointercancel="onEnd"
    @lostpointercapture="onEnd"
    @keydown="onKey"
    @dblclick="restablecer"
  >
    <i class="linea" aria-hidden="true" />
    <i class="grip" aria-hidden="true"><b /><b /><b /></i>
  </div>
</template>

<style scoped>
.divisor {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 13px;
  translate: -50% 0;
  z-index: 7;
  cursor: col-resize;
  touch-action: none;
  outline: none;
}
.der {
  translate: 50% 0;
}
.linea {
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 2px;
  translate: -50% 0;
  border-radius: 2px;
  background: var(--accent);
  opacity: 0;
  scale: 1 0.6;
  transition: opacity 0.25s var(--ease-out), scale 0.45s var(--spring);
}
.grip {
  position: absolute;
  left: 50%;
  top: 50%;
  translate: -50% -50%;
  width: 9px;
  height: 34px;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 4px;
  border-radius: 99px;
  background: var(--bg);
  box-shadow: inset 0 0 0 1px var(--line-2);
  opacity: 0.55;
  transition: opacity 0.25s var(--ease-out), box-shadow 0.25s var(--ease-out), height 0.4s var(--spring);
}
.grip b {
  width: 3px;
  height: 3px;
  border-radius: 50%;
  background: var(--text-3);
  transition: background 0.25s var(--ease-out);
}
.divisor:hover .linea,
.divisor:focus-visible .linea,
.arrastrando .linea {
  opacity: 1;
  scale: 1 1;
}
.divisor:hover .grip,
.divisor:focus-visible .grip,
.arrastrando .grip {
  opacity: 1;
  height: 44px;
  box-shadow: inset 0 0 0 1.5px var(--accent), 0 0 0 4px var(--accent-soft);
}
.divisor:hover .grip b,
.divisor:focus-visible .grip b,
.arrastrando .grip b {
  background: var(--accent);
}
:root[data-motion='soft'] .linea {
  scale: 1 1;
  transition: opacity 0.15s;
}
:root[data-motion='soft'] .grip {
  transition: opacity 0.15s, box-shadow 0.15s;
}
:global(html.orq-redimensionando),
:global(html.orq-redimensionando *) {
  cursor: col-resize !important;
  user-select: none !important;
}
:global(html.orq-redimensionando iframe) {
  pointer-events: none !important;
}
</style>
