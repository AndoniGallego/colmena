<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { debeFundirTextoResumen, partesResumen, textoResumen } from '../../lib/notchCeldas'
import {
  claveAvisoNotch,
  debeCerrarPanelAlPerderFoco,
  reducirFocoNotch,
  type AccionFocoNotch,
} from '../../lib/notchFoco'
import { esCampoTextoNotch } from '../../lib/notchTeclado'
import { crearPuente } from '../../lib/notchPuente'
import { useNow } from '../../lib/time'
import { vaciarCola } from '../../lib/notasCola'
import { auth } from '../../state/app'
import { crearNota, pendientes } from '../../state/notas'
import {
  abrirColmena,
  abrirSesion,
  alternarPanel,
  celdas,
  cerrarNotas,
  cerrarPanel,
  enVivo,
  grupos,
  modo,
  sesiones,
  setPuente,
  iniciarEscuchaNotas,
} from '../../state/notch'
import { brilloPillDesdeAviso, ETIQUETA_AVISO } from '../../lib/notchAvisos'
import { avisoActual, cerrarAviso, iniciarAvisosNotch } from '../../state/notchAvisos'
import { iniciarResumenVisible, resumenVisible } from '../../state/notchResumen'
import { initPedidosPestana } from '../../state/pedidosPestana'
import { gsap, isSoft, useGsap } from '../../motion'
import LogoPanal from '../logo/LogoPanal.vue'
import NotchLogin from './NotchLogin.vue'
import NotchAviso from './NotchAviso.vue'
import NotchCaptura from './NotchCaptura.vue'
import NotchNotas from './NotchNotas.vue'
import NotchPanel from './NotchPanel.vue'
import NotchPill from './NotchPill.vue'

const now = useNow()
const foco = ref(false)
const lbl = ref<HTMLElement | null>(null)
const marca = ref<HTMLElement | null>(null)
const { run } = useGsap()

const partes = computed(() => partesResumen(resumenVisible.value))

const etiquetaAviso = computed(() =>
  auth.value === 'ready' && modo.value === 'aviso' && avisoActual.value
    ? ETIQUETA_AVISO[avisoActual.value.kind]
    : '',
)

const brilloPill = computed(() =>
  brilloPillDesdeAviso(auth.value, modo.value, avisoActual.value),
)
let textoResumenAnterior = ''

function aplicarFoco(accion: AccionFocoNotch) {
  foco.value = reducirFocoNotch(foco.value, accion)
}

function onAlternar() {
  aplicarFoco({ tipo: 'alternar', eraPanel: modo.value === 'panel' })
  alternarPanel()
}

function onEsc(e: KeyboardEvent) {
  if (e.key !== 'Escape' || (modo.value !== 'panel' && modo.value !== 'notas')) return
  if (esCampoTextoNotch(e.target)) return
  aplicarFoco({ tipo: 'esc' })
  if (modo.value === 'notas') cerrarNotas()
  else cerrarPanel()
}

// ---------- notas ----------
/** La captura sigue montada mientras la pastilla se cierra; la clave la renueva en cada apertura. */
const capturaVisible = ref(false)
const capturaClave = ref(0)
const confirmacion = ref<{ texto: string; sinConexion: boolean } | null>(null)
const SIN_CONEXION = 'sin conexión, la guardo cuando vuelva'
const CIERRE_CAPTURA_MS = 700
/** Tras guardar, el renglón nuevo entra en la lista y el notch se cierra este tiempo después. */
const CIERRE_GUARDADA_MS = 700
let capturaTimer: ReturnType<typeof setTimeout> | undefined
let confirmacionTimer: ReturnType<typeof setTimeout> | undefined
let guardadaTimer: ReturnType<typeof setTimeout> | undefined
let guardadaPendiente: { tipo: 'recordatorio' | 'apunte'; sinConexion: boolean } | null = null

watch(modo, (m) => {
  clearTimeout(capturaTimer)
  if (m !== 'notas' && guardadaPendiente) confirmarGuardada()
  if (m === 'notas') {
    capturaClave.value++
    capturaVisible.value = true
  } else if (m !== 'cerrado') {
    capturaVisible.value = false
  } else if (capturaVisible.value) {
    capturaTimer = setTimeout(() => {
      if (modo.value === 'cerrado') capturaVisible.value = false
    }, CIERRE_CAPTURA_MS)
  }
})

function onNotaGuardada(r: { tipo: 'recordatorio' | 'apunte'; sinConexion: boolean }) {
  clearTimeout(guardadaTimer)
  guardadaPendiente = r
  guardadaTimer = setTimeout(() => {
    confirmarGuardada()
    cerrarNotas()
  }, CIERRE_GUARDADA_MS)
}

/** Muestra "Guardada · …" (o el aviso sin conexión). Si el modo cambia antes del cierre, sale en el acto. */
function confirmarGuardada() {
  const r = guardadaPendiente
  if (!r) return
  guardadaPendiente = null
  clearTimeout(guardadaTimer)
  clearTimeout(confirmacionTimer)
  confirmacion.value = r.sinConexion
    ? { texto: SIN_CONEXION, sinConexion: true }
    : { texto: r.tipo === 'recordatorio' ? 'Guardada · Para hacer' : 'Guardada · Apunte', sinConexion: false }
  confirmacionTimer = setTimeout(() => (confirmacion.value = null), r.sinConexion ? 4000 : 2600)
  latirMarca()
}

/** El notch se cerró tras guardar: la marca late una vez. */
function latirMarca() {
  if (isSoft()) return
  run(() => {
    if (!marca.value) return
    gsap.killTweensOf(marca.value)
    gsap.fromTo(
      marca.value,
      { scale: 1 },
      { scale: 1.12, duration: 0.14, yoyo: true, repeat: 1, delay: 0.45, ease: 'power2.out', clearProps: 'transform' },
    )
  })
}

/** Manda lo que quedó en la cola sin conexión: al quedar listo y cada vez que vuelve la conexión. */
function vaciarNotasPendientes() {
  if (auth.value !== 'ready') return
  void vaciarCola(crearNota)
}

watch(
  auth,
  (a) => {
    if (a === 'ready') vaciarNotasPendientes()
  },
  { immediate: true },
)

watch(enVivo, (vivo, antes) => {
  if (vivo && antes === false) vaciarNotasPendientes()
})

function onBlur() {
  aplicarFoco({ tipo: 'blur' })
  if (debeCerrarPanelAlPerderFoco(modo.value)) {
    cerrarPanel()
  }
}

const sesionAviso = computed(() => {
  const id = avisoActual.value?.session_id
  if (!id) return null
  return sesiones.value.find((s) => s.session_id === id) ?? null
})

/** Tocar el aviso o la captura de notas devuelve el foco a la ventana (en Windows, para poder escribir). */
function onAvisoPointerDown() {
  aplicarFoco({ tipo: 'aviso_tocado' })
}

function abrirDesdeAviso(sid: string) {
  abrirSesion(sid)
  cerrarAviso()
}

onMounted(() => {
  document.documentElement.classList.add('notch')
  setPuente(crearPuente())
  iniciarEscuchaNotas()
  iniciarAvisosNotch()
  initPedidosPestana()
  iniciarResumenVisible()
  window.addEventListener('keydown', onEsc)
  window.addEventListener('blur', onBlur)
})

onBeforeUnmount(() => {
  clearTimeout(capturaTimer)
  clearTimeout(guardadaTimer)
  clearTimeout(confirmacionTimer)
  document.documentElement.classList.remove('notch')
  window.removeEventListener('keydown', onEsc)
  window.removeEventListener('blur', onBlur)
})

watch(modo, (m) => {
  aplicarFoco({ tipo: 'modo_cambio', modo: m })
})

watch(avisoActual, (a, prev) => {
  aplicarFoco({
    tipo: 'aviso_cambio',
    clave: claveAvisoNotch(a),
    claveAnterior: claveAvisoNotch(prev),
  })
})

function reposarLbl() {
  if (!lbl.value) return
  gsap.killTweensOf(lbl.value)
  gsap.set(lbl.value, { opacity: 1, y: 0 })
}

watch(
  resumenVisible,
  (r) => {
    const next = textoResumen(r)
    const prev = textoResumenAnterior
    textoResumenAnterior = next
    if (!lbl.value) return
    if (!debeFundirTextoResumen(prev, next, isSoft())) {
      run(reposarLbl)
      return
    }
    run(() => {
      gsap.killTweensOf(lbl.value)
      gsap.to(lbl.value, {
        opacity: 0,
        y: -5,
        duration: 0.15,
        overwrite: 'auto',
        onComplete: () => {
          gsap.fromTo(lbl.value!, { opacity: 0, y: 5 }, { opacity: 1, y: 0, duration: 0.3, ease: 'power2.out', overwrite: 'auto' })
        },
      })
    })
  },
  { flush: 'post' },
)
</script>

<template>
  <NotchPill :modo="modo" :foco="foco" :brillo="brilloPill" :pendientes="pendientes" @alternar="onAlternar">
    <template #cara>
      <span ref="marca" class="mark-wrap">
        <LogoPanal
          v-if="auth === 'checking'"
          :size="30"
          :loader="true"
          :intro="false"
        />
        <LogoPanal
          v-else-if="auth === 'login' || auth === 'forbidden' || auth === 'offline'"
          :size="30"
          :live="false"
          :intro="false"
        />
        <LogoPanal
          v-else
          :size="30"
          :cells="celdas"
          :live="enVivo"
          :intro="false"
        />
      </span>
      <span
        v-if="confirmacion && auth !== 'login'"
        class="lbl lbl-nota"
        :class="{ 'sin-conexion': confirmacion.sinConexion }"
        role="status"
      >{{ confirmacion.texto }}</span>
      <span v-else-if="auth === 'login'" class="lbl">Entrá con tu PIN</span>
      <span v-else-if="auth === 'forbidden' || auth === 'offline'" class="lbl">Sin conexión</span>
      <span
        v-else-if="etiquetaAviso"
        class="lbl lbl-aviso"
        :class="`k-${avisoActual!.kind}`"
      >
        <span class="k-dot" aria-hidden="true" />{{ etiquetaAviso }}
      </span>
      <span v-else ref="lbl" class="lbl">
        <template v-if="!partes.length">Todo tranquilo</template>
        <template v-else>
          <template v-for="(p, i) in partes" :key="i">
            <b v-if="p.alerta" class="need">{{ p.texto }}</b>
            <b v-else>{{ p.texto }}</b>
            <span v-if="i < partes.length - 1" class="sep" aria-hidden="true">·</span>
          </template>
        </template>
      </span>
    </template>
    <template #cuerpo>
      <NotchLogin v-if="auth === 'login'" />
      <NotchAviso
        v-else-if="auth === 'ready' && modo === 'aviso' && avisoActual"
        :aviso="avisoActual"
        :sesion="sesionAviso"
        :now="now"
        @pointerdown="onAvisoPointerDown"
        @cerrar="cerrarAviso"
        @abrir-sesion="abrirDesdeAviso"
      />
      <NotchNotas v-else-if="capturaVisible" :key="capturaClave" :anotar="false" @pointerdown="onAvisoPointerDown">
        <NotchCaptura @guardada="onNotaGuardada" @cerrar="cerrarNotas" />
      </NotchNotas>
      <NotchPanel
        v-else-if="auth === 'ready'"
        :grupos="grupos"
        :now="now"
        @abrir-sesion="abrirSesion"
        @abrir-colmena="abrirColmena"
      />
    </template>
  </NotchPill>
</template>

<style>
html.notch,
html.notch[data-theme='dark'],
html.notch[data-theme='light'] {
  color-scheme: normal;
}
html.notch,
html.notch body {
  background: transparent;
  overflow: hidden;
}
html.notch body::after {
  display: none;
}
html.notch .fx-layer {
  display: none;
}
</style>

<style scoped>
.mark-wrap {
  --mark-ink: var(--text);
  --mark-lit: var(--accent);
  --mark-dim: color-mix(in srgb, var(--text) 15%, transparent);
  --mark-alert: var(--st-blocked);
  width: 30px;
  height: 30px;
  flex: none;
  display: block;
}
.lbl {
  font-size: 0.84rem;
  color: var(--text-2);
  white-space: nowrap;
}
.lbl b {
  color: var(--text);
  font-weight: 600;
}
.lbl b.need {
  color: var(--st-blocked);
}
.sep {
  padding-inline: 0.28em;
  color: var(--text-3);
  font-weight: 400;
}
.lbl-aviso {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text);
  font-weight: 600;
  letter-spacing: 0.01em;
}
.lbl-aviso.k-done {
  --k: var(--st-done);
}
.lbl-aviso.k-asks {
  --k: var(--st-working);
}
.lbl-aviso.k-blocked {
  --k: var(--st-blocked);
}
.lbl-nota {
  color: var(--text);
  font-weight: 600;
}
.lbl-nota.sin-conexion {
  color: var(--miel);
}
.k-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--k);
  box-shadow:
    0 0 0 3px color-mix(in srgb, var(--k) 18%, transparent),
    0 0 10px var(--k);
}
</style>
