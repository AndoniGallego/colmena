<script setup lang="ts">
import { Terminal } from '@xterm/xterm'
import '@xterm/xterm/css/xterm.css'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { desktop } from '../lib/viewport'
import {
  ConexionVivo,
  MSG_SESION_VENCIDA,
  textoEstado,
  type EstadoVivo,
  type FotoVivo,
} from '../lib/vivo'
import { gsap, isSoft, useGsap } from '../motion'
import {
  debeAbrirPin,
  formatoVentana,
  agrupadorEntrada,
  manejarErrorEscritura,
  mensajeEntrada,
  rotuloTecla,
  mensajeTecla,
  TECLAS_BARRA,
  type TeclaBarra,
} from '../lib/vivoEscritura'
import { debeMostrarPinAlAbrir } from '../lib/abrirTerminalCliente'
import { consumirPedirPinAlAbrir, cerrarVivo, loadTerminalConfig, vivoAbierto } from '../state/terminalVivo'
import { countdown, forgetVentana, openVentana, pinProblem, touchVentana, ventana, ventanaAbierta } from '../state/terminalWrite'
import { tconfig } from '../state/terminalActions'
import { useFocusTrap } from '../lib/focusTrap'
import Icon from './Icon.vue'
import LogoLoader from './LogoLoader.vue'
import TerminalPinSheet from './TerminalPinSheet.vue'

const LETRA_KEY = 'colmena.vivo.letra'
const LETRA_MIN = 8
const LETRA_MAX = 20

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const closeBtn = ref<HTMLButtonElement | null>(null)
const host = ref<HTMLElement | null>(null)
const scroll = ref<HTMLElement | null>(null)

const estado = ref<EstadoVivo>('conectando')
const mensaje = ref<string | undefined>()
const codigoTermino = ref<number | null>(null)
const puedeReintentar = ref(false)
const ajustarAncho = ref(false)
const columnas = ref(80)
const filas = ref(24)
const escribiendo = ref(false)
const abierto = computed(() => !!vivoAbierto.value)
const { onKeydown: trapKeydown } = useFocusTrap(root, () => abierto.value, {
  onEscape: () => {
    if (!escribiendo.value) cerrar()
  },
  initial: () => closeBtn.value,
})
const avisoEscritura = ref('')
const pinSheet = ref({ open: false, busy: false, error: null as string | null, lockedUntil: null as number | null })
const textoMovil = ref('')
const inputMovil = ref<HTMLInputElement | null>(null)

let term: Terminal | null = null
let onDataVivo: { dispose(): void } | null = null
const tanda = agrupadorEntrada((texto) => {
  if (!ventana.token || !escribiendo.value) return
  conexion?.enviar(mensajeEntrada(ventana.token, texto))
  touchVentana()
})
let conexion: ConexionVivo | null = null
let ro: ResizeObserver | null = null
let themeObs: MutationObserver | null = null

const letraDefault = () => (desktop.value ? 13 : 11)

function leerLetra(): number {
  try {
    const raw = localStorage.getItem(LETRA_KEY)
    if (raw === null) return letraDefault()
    const n = Number(raw)
    if (!Number.isFinite(n)) return letraDefault()
    return Math.min(LETRA_MAX, Math.max(LETRA_MIN, Math.round(n)))
  } catch {
    return letraDefault()
  }
}

const letra = ref(leerLetra())

function guardarLetra(n: number): void {
  letra.value = n
  try {
    localStorage.setItem(LETRA_KEY, String(n))
  } catch {
    /* noop */
  }
  if (term) term.options.fontSize = n
  if (ajustarAncho.value) void nextTick(recalcularAjuste)
}

function cambiarLetra(delta: number): void {
  ajustarAncho.value = false
  guardarLetra(Math.min(LETRA_MAX, Math.max(LETRA_MIN, letra.value + delta)))
}

function temaXterm(): Record<string, string> {
  const s = getComputedStyle(document.documentElement)
  const pick = (v: string) => s.getPropertyValue(v).trim()
  return {
    background: pick('--term-bg'),
    foreground: pick('--term-fg'),
    cursor: pick('--term-fg'),
    black: pick('--ansi-0'),
    red: pick('--ansi-1'),
    green: pick('--ansi-2'),
    yellow: pick('--ansi-3'),
    blue: pick('--ansi-4'),
    magenta: pick('--ansi-5'),
    cyan: pick('--ansi-6'),
    white: pick('--ansi-7'),
    brightBlack: pick('--ansi-8'),
    brightRed: pick('--ansi-9'),
    brightGreen: pick('--ansi-10'),
    brightYellow: pick('--ansi-11'),
    brightBlue: pick('--ansi-12'),
    brightMagenta: pick('--ansi-13'),
    brightCyan: pick('--ansi-14'),
    brightWhite: pick('--ansi-15'),
  }
}

function fontMono(): string {
  return getComputedStyle(document.documentElement).getPropertyValue('--font-mono').trim() || 'monospace'
}

function bloquearTeclado(): void {
  if (!term) return
  term.options.disableStdin = true
  const ta = term.element?.querySelector('textarea')
  if (!ta) return
  ta.setAttribute('inputmode', 'none')
  ta.setAttribute('readonly', 'true')
  ta.setAttribute('tabindex', '-1')
}

function desactivarEscritura(): void {
  escribiendo.value = false
  onDataVivo?.dispose()
  onDataVivo = null
  tanda.cancelar()
  if (term) term.options.disableStdin = true
  bloquearTeclado()
}

function activarEscrituraPc(): void {
  if (!term) return
  term.options.disableStdin = false
  const ta = term.element?.querySelector('textarea')
  if (ta) {
    ta.removeAttribute('readonly')
    ta.removeAttribute('inputmode')
    ta.setAttribute('tabindex', '0')
    ta.focus()
  }
  onDataVivo?.dispose()
  onDataVivo = term.onData((data: string) => tanda.push(data))
}

function enviarTextoMovil(extra = ''): void {
  const base = textoMovil.value + extra
  if (!base || !ventana.token) return
  conexion?.enviar(mensajeEntrada(ventana.token, base))
  touchVentana()
  textoMovil.value = ''
}

function enviarTeclaMovil(tecla: TeclaBarra): void {
  if (!ventana.token) return
  conexion?.enviar(mensajeTecla(ventana.token, tecla))
  touchVentana()
}

function onErrorEscritura(codigo: 'ventana' | 'apagado' | 'caido'): void {
  const r = manejarErrorEscritura(codigo)
  desactivarEscritura()
  avisoEscritura.value = r.aviso
  if (r.forget) forgetVentana()
}

async function encenderEscritura(): Promise<void> {
  avisoEscritura.value = ''
  escribiendo.value = true
  if (desktop.value) nextTick(() => activarEscrituraPc())
  else await nextTick(() => inputMovil.value?.focus())
}

async function toggleTeclado(): Promise<void> {
  if (escribiendo.value) {
    desactivarEscritura()
    avisoEscritura.value = ''
    return
  }
  if (debeAbrirPin(ventanaAbierta.value, true)) {
    pinSheet.value = { open: true, busy: false, error: null, lockedUntil: null }
    return
  }
  await encenderEscritura()
}

async function confirmarPin(value: string): Promise<void> {
  pinSheet.value.busy = true
  pinSheet.value.error = null
  try {
    await openVentana(value)
  } catch (e) {
    const p = pinProblem(e)
    pinSheet.value.error = p.message
    pinSheet.value.lockedUntil = p.retryAfter ? Date.now() + p.retryAfter * 1000 : null
    pinSheet.value.busy = false
    return
  }
  pinSheet.value = { open: false, busy: false, error: null, lockedUntil: null }
  await encenderEscritura()
}

function cancelarPin(): void {
  pinSheet.value.open = false
}

function quizasAbrirPinAlMontar(): void {
  if (!consumirPedirPinAlAbrir()) return
  if (!debeMostrarPinAlAbrir(true, ventanaAbierta.value)) return
  pinSheet.value = { open: true, busy: false, error: null, lockedUntil: null }
}

function aplicarFoto(f: FotoVivo): void {
  if (!term) return
  columnas.value = f.columnas
  filas.value = f.filas
  term.reset()
  term.resize(f.columnas, f.filas)
  term.write(f.texto)
  void nextTick(() => {
    bloquearTeclado()
    if (ajustarAncho.value) recalcularAjuste()
  })
}

function recalcularAjuste(): void {
  if (!term || !scroll.value || !ajustarAncho.value) return
  const pantalla = term.element?.querySelector('.xterm-screen') as HTMLElement | null
  if (!pantalla || columnas.value < 1) return
  const anchoDisp = scroll.value.clientWidth - 16
  if (anchoDisp <= 0) return
  const celda = pantalla.getBoundingClientRect().width / columnas.value
  if (!celda || !Number.isFinite(celda)) return
  const objetivo = Math.min(LETRA_MAX, Math.max(6, Math.floor((letra.value * anchoDisp) / (celda * columnas.value))))
  if (objetivo !== letra.value) {
    letra.value = objetivo
    term.options.fontSize = objetivo
  }
}

function toggleAjuste(): void {
  ajustarAncho.value = !ajustarAncho.value
  if (ajustarAncho.value) recalcularAjuste()
  else guardarLetra(leerLetra())
}

function montarTerm(): void {
  term = new Terminal({
    disableStdin: true,
    cursorBlink: false,
    convertEol: false,
    scrollback: 5000,
    fontFamily: fontMono(),
    fontSize: letra.value,
    theme: temaXterm(),
  })
  if (host.value) {
    term.open(host.value)
    bloquearTeclado()
  }
}

function montarConexion(paneId: string): void {
  conexion?.cerrar()
  conexion = new ConexionVivo({
    paneId,
    loc: location,
    deps: {
      crearSocket: (url) => new WebSocket(url) as unknown as import('../lib/vivo').WebSocketLike,
      setTimeout: (fn, ms) => window.setTimeout(fn, ms),
      clearTimeout: (id) => window.clearTimeout(id),
    },
    onFoto: aplicarFoto,
    onSalida: (t) => term?.write(t),
    onEstado: (e, msg, extra) => {
      estado.value = e
      mensaje.value = msg
      if (extra?.codigo !== undefined) codigoTermino.value = extra.codigo
      puedeReintentar.value = !!extra?.reintentar
    },
    onErrorEscritura: (codigo) => onErrorEscritura(codigo),
  })
  conexion.abrir()
}

function observar(): void {
  themeObs = new MutationObserver(() => {
    if (term) term.options.theme = temaXterm()
  })
  themeObs.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] })
  if (scroll.value) {
    ro = new ResizeObserver(() => {
      if (ajustarAncho.value) recalcularAjuste()
    })
    ro.observe(scroll.value)
  }
}

function limpiar(): void {
  desactivarEscritura()
  avisoEscritura.value = ''
  pinSheet.value.open = false
  conexion?.cerrar()
  conexion = null
  ro?.disconnect()
  ro = null
  themeObs?.disconnect()
  themeObs = null
  term?.dispose()
  term = null
}

function cerrar(): void {
  limpiar()
  cerrarVivo()
}

function reintentar(): void {
  estado.value = 'conectando'
  mensaje.value = undefined
  puedeReintentar.value = false
  conexion?.reintentar()
}

function onKey(e: KeyboardEvent): void {
  // Escribiendo, Escape es para la terminal (los diálogos de Claude lo usan), no para cerrar el visor.
  if (e.key === 'Escape' && abierto.value && !escribiendo.value && !root.value?.contains(document.activeElement as Node)) cerrar()
}

function onOnline(): void {
  conexion?.despertar()
}

function onVis(): void {
  if (document.visibilityState === 'visible') conexion?.despertar()
}

const titulo = computed(() => vivoAbierto.value?.titulo ?? '')
const chipClase = computed(() => estado.value)
const rotuloChip = computed(() => textoEstado(estado.value))
const escrituraRemota = computed(() => tconfig.value?.escritura === true)
const relojVentana = computed(() => formatoVentana(countdown.value))

watch(countdown, (n) => {
  if (escribiendo.value && n <= 0) {
    desactivarEscritura()
    avisoEscritura.value = 'Se cerró la ventana de escritura'
    forgetVentana()
  }
})

watch(ventanaAbierta, (on) => {
  if (!on && escribiendo.value) desactivarEscritura()
})

const overlayCentro = computed(
  () =>
    estado.value === 'conectando' ||
    estado.value === 'terminada' ||
    estado.value === 'cerrada' ||
    estado.value === 'caido' ||
    estado.value === 'error',
)
const bandaReconectando = computed(() => estado.value === 'reconectando')

const textoOverlay = computed(() => {
  if (estado.value === 'terminada') {
    return codigoTermino.value != null ? `La sesión terminó (${codigoTermino.value})` : 'La sesión terminó'
  }
  if (estado.value === 'cerrada') return 'La sesión se cerró'
  if (estado.value === 'caido') return 'Las terminales propias no responden. Reintento solo…'
  if (estado.value === 'error') return mensaje.value ?? MSG_SESION_VENCIDA
  return ''
})

watch(
  () => vivoAbierto.value?.paneId,
  (id) => {
    limpiar()
    if (!id) return
    estado.value = 'conectando'
    mensaje.value = undefined
    codigoTermino.value = null
    puedeReintentar.value = false
    nextTick(() => {
      montarTerm()
      observar()
      montarConexion(id)
      quizasAbrirPinAlMontar()
      if (root.value && !isSoft()) {
        run(() =>
          gsap.from(root.value!.querySelectorAll('.vhead > *'), {
            y: -10,
            opacity: 0,
            duration: 0.5,
            ease: 'power3.out',
            stagger: 0.05,
            delay: 0.1,
          }),
        )
      }
    })
  },
  { immediate: true },
)

onMounted(() => {
  if (!tconfig.value) void loadTerminalConfig()
  window.addEventListener('keydown', onKey)
  window.addEventListener('online', onOnline)
  document.addEventListener('visibilitychange', onVis)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  window.removeEventListener('online', onOnline)
  document.removeEventListener('visibilitychange', onVis)
  limpiar()
})
</script>

<template>
  <Transition name="ov">
    <div v-if="abierto" class="ov" :class="{ desktop }" @click.self="cerrar">
      <div ref="root" class="card" :class="{ escribiendo }" role="dialog" aria-modal="true" :aria-label="`Terminal en vivo: ${titulo}`" @keydown="trapKeydown">
        <header class="vhead">
          <button ref="closeBtn" type="button" class="x hit" aria-label="Cerrar" @click="cerrar"><Icon name="close" :size="16" /></button>
          <h1 class="tit" :title="titulo">{{ titulo }}</h1>
          <span class="chip" :class="chipClase" role="status"><i class="dot" aria-hidden="true" />{{ rotuloChip }}</span>
          <span v-if="escribiendo" class="write-tag mono">Escribiendo · {{ relojVentana }}</span>
          <span v-else class="ro-tag">solo lectura</span>
          <button
            v-if="escrituraRemota"
            type="button"
            class="kbd-btn"
            :aria-pressed="escribiendo"
            @click="toggleTeclado"
          >
            <Icon name="keyboard" :size="14" /><span>Teclado</span>
          </button>
          <div class="zoom" role="group" aria-label="Tamaño de letra">
            <button type="button" class="zbtn" aria-label="Achicar letra" @click="cambiarLetra(-1)"><Icon name="minus" :size="14" /></button>
            <button type="button" class="zbtn" aria-label="Agrandar letra" @click="cambiarLetra(1)"><Icon name="plus" :size="14" /></button>
          </div>
          <button
            type="button"
            class="fit hit"
            :aria-pressed="ajustarAncho"
            @click="toggleAjuste"
          >
            <Icon :name="ajustarAncho ? 'shrink' : 'expand'" :size="14" /><span>Ajustar al ancho</span>
          </button>
        </header>

        <div v-if="bandaReconectando" class="banda" role="status">Reconectando…</div>
        <div v-if="avisoEscritura" class="banda aviso" role="status">{{ avisoEscritura }}</div>

        <div ref="scroll" class="scroll">
          <div ref="host" class="term-host" />
          <Transition name="fade">
            <div v-if="overlayCentro" class="velo">
              <LogoLoader v-if="estado === 'conectando'" />
              <div v-else class="velo-msg">
                <p>{{ textoOverlay }}</p>
                <button v-if="estado === 'error' && puedeReintentar" type="button" class="retry" @click="reintentar">
                  <Icon name="refresh" :size="14" /> Reintentar
                </button>
              </div>
            </div>
          </Transition>
        </div>
        <div v-if="escribiendo && !desktop" class="movil-teclado">
          <div class="teclas" role="toolbar" aria-label="Teclas especiales">
            <button v-for="t in TECLAS_BARRA" :key="t" type="button" class="tkey" :aria-label="t" @click="enviarTeclaMovil(t)">{{ rotuloTecla(t) }}</button>
          </div>
          <div class="enviar-fila">
            <input
              ref="inputMovil"
              v-model="textoMovil"
              class="movil-in"
              type="text"
              enterkeyhint="send"
              autocomplete="off"
              autocapitalize="off"
              spellcheck="false"
              aria-label="Texto para la terminal"
              @keydown.enter.prevent="enviarTextoMovil('\r')"
            />
            <button type="button" class="enviar-btn" aria-label="Enviar" @click="enviarTextoMovil('\r')"><Icon name="arrow-right" :size="16" /></button>
          </div>
        </div>
      </div>
      <TerminalPinSheet
        :open="pinSheet.open"
        :busy="pinSheet.busy"
        :error="pinSheet.error"
        :locked-until="pinSheet.lockedUntil"
        :capa="95"
        @submit="confirmarPin"
        @close="cancelarPin"
      />
    </div>
  </Transition>
</template>

<style scoped>
.ov {
  position: fixed;
  inset: 0;
  z-index: 85;
  background: var(--bg);
  padding: env(safe-area-inset-top) env(safe-area-inset-right) env(safe-area-inset-bottom) env(safe-area-inset-left);
}
.ov.desktop {
  display: flex;
  justify-content: flex-end;
  background: color-mix(in srgb, var(--bg) 55%, transparent);
  backdrop-filter: blur(3px);
}
.card {
  display: flex;
  flex-direction: column;
  width: 100%;
  height: 100dvh;
  max-height: 100dvh;
  background: var(--surface);
}
.desktop .card {
  width: min(92%, 1400px);
  height: 100%;
  max-height: none;
  margin: 12px 12px 12px 0;
  border-radius: var(--r-lg);
  box-shadow: -24px 0 60px -30px rgba(0, 0, 0, 0.6), 0 0 0 1px var(--line);
  overflow: hidden;
}
.card.escribiendo {
  box-shadow: -24px 0 60px -30px rgba(0, 0, 0, 0.6), 0 0 0 2px var(--accent-line);
}
.ov:not(.desktop) .card.escribiendo {
  box-shadow: 0 0 0 2px var(--accent-line);
}
.vhead {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 10px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--line);
  min-width: 0;
}
.tit {
  flex: 1 1 120px;
  min-width: 0;
  margin: 0;
  font-size: 15px;
  font-weight: 620;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.x {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-md);
  color: var(--text-2);
}
.x:hover {
  background: var(--surface-hover);
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: 560;
  color: var(--text-2);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line);
}
.chip.en_vivo {
  color: var(--st-working);
  background: var(--st-working-soft);
}
.chip.reconectando,
.chip.caido {
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
}
.chip.terminada,
.chip.cerrada,
.chip.error {
  color: var(--text-3);
  background: var(--st-idle-soft);
}
.chip.error {
  color: var(--danger);
  background: var(--danger-soft);
}
.dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: currentColor;
}
.chip.en_vivo .dot {
  background: var(--st-working);
  animation: pulso 1.6s var(--ease-in-out) infinite;
}
@keyframes pulso {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
  }
  50% {
    opacity: 0.45;
    transform: scale(0.85);
  }
}
:root[data-motion='soft'] .chip.en_vivo .dot {
  animation: none;
}
.ro-tag,
.write-tag {
  font-size: 11px;
  color: var(--text-4);
  letter-spacing: 0.02em;
}
.write-tag {
  color: var(--accent);
  font-weight: 600;
}
.kbd-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border-radius: var(--r-md);
  font-size: 12px;
  font-weight: 560;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.kbd-btn[aria-pressed='true'] {
  color: var(--accent-ink);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.banda.aviso {
  color: var(--text-2);
  background: var(--surface-2);
}
.movil-teclado {
  padding: 8px 10px calc(8px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--line);
  background: var(--surface);
  display: grid;
  gap: 8px;
}
.teclas {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tkey {
  height: 34px;
  padding: 0 10px;
  border-radius: 8px;
  font-size: 11px;
  font-family: var(--font-mono);
  text-transform: uppercase;
  color: var(--text-2);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.enviar-fila {
  display: flex;
  gap: 8px;
}
.movil-in {
  flex: 1;
  min-width: 0;
  height: 40px;
  padding: 0 12px;
  border-radius: var(--r-md);
  font-family: var(--font-mono);
  font-size: 14px;
  color: var(--text);
  background: var(--term-bg);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.enviar-btn {
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: var(--r-md);
  color: var(--accent-ink);
  background: var(--accent);
}
.zoom {
  display: flex;
  gap: 4px;
}
.zbtn,
.fit {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 32px;
  padding: 0 10px;
  border-radius: var(--r-md);
  font-size: 12px;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.zbtn {
  width: 32px;
  padding: 0;
}
.fit span {
  display: none;
}
.desktop .fit span {
  display: inline;
}
@media (min-width: 480px) {
  .fit span {
    display: inline;
  }
}
.scroll {
  position: relative;
  flex: 1;
  min-height: 0;
  overflow: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  background: var(--term-bg);
}
.desktop .scroll {
  margin: 0 12px 12px;
  border-radius: var(--r-md);
}
.term-host {
  display: inline-block;
  min-width: min-content;
  padding: 8px;
}
.banda {
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 560;
  text-align: center;
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  border-bottom: 1px solid var(--line);
}
.velo {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  background: color-mix(in srgb, var(--term-bg) 72%, transparent);
  padding: 24px;
}
.velo-msg {
  text-align: center;
  max-width: 28rem;
}
.velo-msg p {
  margin: 0 0 12px;
  font-size: 15px;
  color: var(--text);
}
.retry {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 40px;
  padding: 0 16px;
  border-radius: 12px;
  font-weight: 560;
  color: var(--accent-ink);
  background: var(--accent);
}
.ov-enter-active {
  transition: opacity 0.25s;
}
.ov-enter-active .card {
  transition: transform 0.55s var(--spring);
}
.ov-leave-active {
  transition: opacity 0.2s;
}
.ov-enter-from,
.ov-leave-to {
  opacity: 0;
}
.ov-enter-from .card {
  transform: translateX(40px);
}
.ov:not(.desktop).ov-enter-from .card {
  transform: translateY(6%);
}
:root[data-motion='soft'] .ov-enter-from .card {
  transform: none;
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.25s var(--ease-out);
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
:root[data-motion='soft'] .fade-enter-active,
:root[data-motion='soft'] .fade-leave-active {
  transition-duration: 0.12s;
}
@media (max-width: 520px) {
  .ro-tag {
    order: 10;
    width: 100%;
  }
  .vhead {
    padding-top: max(10px, env(safe-area-inset-top));
  }
}
@media (pointer: coarse) {
  .tkey { min-height: 44px; }
}
</style>
