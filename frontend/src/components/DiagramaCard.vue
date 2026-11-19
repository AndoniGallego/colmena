<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { escenaDe, etiquetaDe, tituloDe } from '../lib/bloque'
import type { Diagrama } from '../lib/diagrama'
import type { Escena } from '../lib/escena'
import { nextOf, numeroPaso, ruta } from '../lib/pasos'
import { ordenRecorrido } from '../lib/pasosEscena'
import { fuentes, medirTexto } from '../lib/medir'
import { openInLibrary } from '../state/biblioteca'
import { finePointer, gsap, haptic, isSoft, useGsap } from '../motion'
import DiagramaSvg from './DiagramaSvg.vue'
import PasosRecuadro from './PasosRecuadro.vue'
import Icon from './Icon.vue'

const props = defineProps<{ diagrama: Diagrama; libId?: string | null; quiet?: boolean; mini?: boolean }>()

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const lienzo = ref<HTMLElement | null>(null)
const dib = ref<InstanceType<typeof DiagramaSvg> | null>(null)
const recuadro = ref<InstanceType<typeof PasosRecuadro> | null>(null)

const titulo = computed(() => tituloDe(props.diagrama))
const resumen = computed(() => props.diagrama.resumen)
const notas = computed(() => props.diagrama.notas)
/** secuencias and procesos can be walked step by step */
const conPasos = computed(() => (props.diagrama.tipo === 'estructura' ? null : props.diagrama))
const etiquetaTipo = computed(() => etiquetaDe(props.diagrama))

// ---------- size & layout ----------
const lw = ref(0)
const lh = ref(0)
const full = ref(false)
const altoChat = () => (typeof window === 'undefined' ? 700 : Math.max(360, Math.min(window.innerHeight * 0.72, 760)))

const escena = computed<Escena>(() => {
  void fuentes.value
  if (full.value && lw.value) return escenaDe(props.diagrama, lw.value - 40, lh.value - 40, medirTexto)
  const w = Math.max(240, Math.round((lw.value || 360) / 24) * 24)
  return escenaDe(props.diagrama, w, props.mini ? 260 : altoChat(), medirTexto)
})

/** In the chat the drawing shrinks to the width it has, never past its natural size. */
const escala = computed(() => {
  const e = escena.value
  const w = lw.value || 360
  if (props.mini) return Math.min(1, w / e.w, (lh.value || 200) / e.h)
  return Math.min(1, w / e.w)
})
const chico = computed(() => !full.value && !props.mini && escala.value < 0.72)

// ---------- full screen, pan & zoom ----------
const vista = reactive({ z: 1, x: 0, y: 0 })
const zMin = computed(() => Math.min(0.2, encaje()))
const Z_MAX = 4

function encaje() {
  const e = escena.value
  if (!lw.value || !lh.value) return 1
  return Math.min(1.6, (lw.value - 40) / e.w, (lh.value - 40) / e.h)
}

function encajar(animar = false) {
  const e = escena.value
  const z = Math.max(0.15, encaje())
  const fin = { z, x: (lw.value - e.w * z) / 2, y: (lh.value - e.h * z) / 2 }
  if (animar && !isSoft()) run(() => gsap.to(vista, { ...fin, duration: 0.45, ease: 'power3.out' }))
  else Object.assign(vista, fin)
}

function zoomEn(f: number, cx = lw.value / 2, cy = lh.value / 2) {
  gsap.killTweensOf(vista)
  const z = Math.min(Z_MAX, Math.max(zMin.value, vista.z * f))
  const k = z / vista.z
  vista.x = cx - (cx - vista.x) * k
  vista.y = cy - (cy - vista.y) * k
  vista.z = z
  limitar()
}

/** Keeps at least a corner of the drawing on screen. */
function limitar() {
  const e = escena.value
  const w = e.w * vista.z
  const h = e.h * vista.z
  const m = 80
  vista.x = Math.min(lw.value - m, Math.max(m - w, vista.x))
  vista.y = Math.min(lh.value - m, Math.max(m - h, vista.y))
}

const holderH = ref(0)
function setFull(v: boolean) {
  if (v === full.value || props.mini) return
  if (v) holderH.value = root.value?.offsetHeight ?? 0
  cerrarDetalle()
  full.value = v
  try {
    document.body.style.overflow = v ? 'hidden' : ''
  } catch {
    /* no body */
  }
  nextTick(() => {
    medir()
    if (v) encajar()
    root.value?.focus({ preventScroll: true })
    if (v && !isSoft() && root.value) run(() => gsap.from(root.value!, { opacity: 0, scale: 0.97, duration: 0.45, ease: 'power3.out' }))
  })
}

const punteros = new Map<number, { x: number; y: number }>()
let gesto: { x: number; y: number; z: number; vx: number; vy: number; dist: number; mx: number; my: number } | null = null
let arrastro = false
let ultimoToque = { t: 0, x: 0, y: 0 }

function local(e: { clientX: number; clientY: number }) {
  const r = lienzo.value!.getBoundingClientRect()
  return { x: e.clientX - r.left, y: e.clientY - r.top }
}
function empezarGesto() {
  const ps = [...punteros.values()]
  const mx = ps.reduce((s, p) => s + p.x, 0) / ps.length
  const my = ps.reduce((s, p) => s + p.y, 0) / ps.length
  const dist = ps.length > 1 ? Math.hypot(ps[0].x - ps[1].x, ps[0].y - ps[1].y) : 0
  gesto = { x: mx, y: my, z: vista.z, vx: vista.x, vy: vista.y, dist, mx, my }
}
function onDown(e: PointerEvent) {
  if (!full.value || (e.target as HTMLElement).closest('button')) return
  if (e.pointerType === 'mouse' && e.button !== 0) return
  gsap.killTweensOf(vista)
  if (!punteros.size) arrastro = false
  punteros.set(e.pointerId, local(e))
  empezarGesto()
  window.addEventListener('pointermove', onMove)
  window.addEventListener('pointerup', onUp)
  window.addEventListener('pointercancel', onUp)
}
function onMove(e: PointerEvent) {
  if (!punteros.has(e.pointerId) || !gesto) return
  punteros.set(e.pointerId, local(e))
  const ps = [...punteros.values()]
  const mx = ps.reduce((s, p) => s + p.x, 0) / ps.length
  const my = ps.reduce((s, p) => s + p.y, 0) / ps.length
  if (!arrastro && Math.hypot(mx - gesto.mx, my - gesto.my) < 6 && ps.length < 2) return
  arrastro = true
  let z = gesto.z
  if (ps.length > 1 && gesto.dist > 0) z = Math.min(Z_MAX, Math.max(zMin.value, gesto.z * (Math.hypot(ps[0].x - ps[1].x, ps[0].y - ps[1].y) / gesto.dist)))
  const k = z / gesto.z
  vista.z = z
  vista.x = mx - (gesto.x - gesto.vx) * k
  vista.y = my - (gesto.y - gesto.vy) * k
  limitar()
}
function onUp(e: PointerEvent) {
  if (!punteros.has(e.pointerId)) return
  const p = punteros.get(e.pointerId)!
  punteros.delete(e.pointerId)
  if (punteros.size) empezarGesto()
  else {
    gesto = null
    window.removeEventListener('pointermove', onMove)
    window.removeEventListener('pointerup', onUp)
    window.removeEventListener('pointercancel', onUp)
    if (!arrastro && e.pointerType !== 'mouse') {
      const now = performance.now()
      if (now - ultimoToque.t < 320 && Math.hypot(p.x - ultimoToque.x, p.y - ultimoToque.y) < 30) {
        ultimoToque.t = 0
        encajar(true)
      } else ultimoToque = { t: now, x: p.x, y: p.y }
    }
  }
}
function onWheel(e: WheelEvent) {
  if (!full.value) return
  e.preventDefault()
  const p = local(e)
  const d = e.deltaMode === 1 ? e.deltaY * 16 : e.deltaY
  zoomEn(Math.exp(-d * (e.ctrlKey ? 0.01 : 0.0018)), p.x, p.y)
}

// ---------- selection & detail ----------
const sel = ref<string | null>(null)
const sobre = ref<string | null>(null)
const hoja = ref(false)
const pop = ref<{ left: number; top: number; w: number } | null>(null)
const popEl = ref<HTMLElement | null>(null)

function vecinos(k: string): Set<string> {
  const s = new Set([k])
  for (const a of escena.value.aristas) {
    if (k.startsWith('n') && (a.de === k || a.a === k)) {
      if (!a.propia || escena.value.tipo !== 'secuencia') s.add(a.key)
      s.add(a.de)
      s.add(a.a)
    }
    if (a.key === k) {
      s.add(a.de)
      s.add(a.a)
    }
  }
  // in a sequence, an actor lights the steps it takes part in
  if (escena.value.tipo === 'secuencia' && k.startsWith('n')) for (const a of escena.value.aristas) if (a.de === k || a.a === k) s.add(a.key)
  return s
}

const foco = computed<Set<string> | null>(() => {
  if (andando.value) return activo.value < pasosPorIndice.value.length ? new Set(pasosPorIndice.value[activo.value]) : null
  const k = sel.value ?? sobre.value
  return k ? vecinos(k) : null
})

const info = computed(() => {
  const k = sel.value
  if (!k) return null
  const e = escena.value
  const nombre = (key: string) => e.nodos.find((n) => n.key === key)?.nombre ?? ''
  if (k.startsWith('n')) {
    const n = e.nodos.find((x) => x.key === k)
    if (!n) return null
    const grupo = n.grupo >= 0 ? (e.grupos.find((g) => g.key === `g${n.grupo}`)?.nombre ?? '') : ''
    const enlaces = e.aristas
      .filter((a) => a.de === k || a.a === k)
      .map((a) => ({ key: a.propia ? a.key : a.de === k ? a.a : a.de, sale: a.de === k, otro: nombre(a.de === k ? a.a : a.de), texto: a.titulo, num: a.num }))
    return { tipo: 'nodo' as const, icono: n.icono, titulo: n.nombre, chip: [n.tipoTexto, grupo].filter(Boolean).join(' · '), detalle: n.detalle, datos: n.datos, sub: n.sub, enlaces }
  }
  const a = e.aristas.find((x) => x.key === k)
  if (!a) return null
  const quien = a.de === a.a ? nombre(a.de) : `${nombre(a.de)} → ${nombre(a.a)}`
  return { tipo: 'paso' as const, icono: '', titulo: a.titulo, chip: `Paso ${a.num} · ${quien}`, detalle: a.detalle, datos: a.datos, sub: '', enlaces: [] }
})

const usaHoja = () => !finePointer() || window.innerWidth < 640

function elegir(k: string | null) {
  if (arrastro) return
  if (andando.value && k) {
    const i = pasosPorIndice.value.findIndex((ks) => ks.includes(k))
    if (i >= 0) return irAPaso(i)
  }
  if (!k || k === sel.value) return cerrarDetalle()
  haptic(6)
  sel.value = k
  if (usaHoja()) {
    pop.value = null
    hoja.value = true
  } else {
    hoja.value = false
    nextTick(ubicarPop)
  }
}

function cerrarDetalle() {
  sel.value = null
  hoja.value = false
  pop.value = null
}

/** Puts the popover beside the chosen thing, on whichever side has room. */
function ubicarPop() {
  const k = sel.value
  const host = root.value
  const el = k ? host?.querySelector(`[data-k="${k}"]`) : null
  if (!host || !el || hoja.value) return
  const r = (el.querySelector('.nd-box, .et-box, .ln') ?? el).getBoundingClientRect()
  const c = host.getBoundingClientRect()
  const w = Math.min(320, c.width - 16)
  const h = popEl.value?.offsetHeight ?? 160
  let left = r.right - c.left + 12
  let top = r.top - c.top + r.height / 2 - h / 2
  if (left + w > c.width - 8) {
    left = r.left - c.left - 12 - w
    if (left < 8) {
      left = Math.min(c.width - w - 8, Math.max(8, r.left - c.left + r.width / 2 - w / 2))
      top = r.bottom - c.top + 10
    }
  }
  const maxTop = full.value ? c.height - h - 8 : Math.max(8, c.height - 24)
  pop.value = { left, top: Math.max(8, Math.min(top, maxTop)), w }
}
watch(() => [vista.x, vista.y, vista.z, escena.value], () => sel.value && !hoja.value && nextTick(ubicarPop))

// ---------- keyboard ----------
function centros() {
  const e = escena.value
  return [
    ...e.nodos.map((n) => ({ k: n.key, x: n.x + n.w / 2, y: n.y + n.h / 2 })),
    ...e.aristas.filter((a) => a.propia && a.etiqueta).map((a) => ({ k: a.key, x: a.etiqueta!.x + a.etiqueta!.w / 2, y: a.etiqueta!.y + a.etiqueta!.h / 2 })),
  ]
}
function mover(dx: number, dy: number) {
  const cs = centros()
  const cur = cs.find((c) => c.k === sel.value)
  if (!cur) {
    const primero = [...cs].sort((a, b) => a.y + a.x * 0.5 - (b.y + b.x * 0.5))[0]
    if (primero) elegirTeclado(primero.k)
    return
  }
  let mejor: { k: string; s: number } | null = null
  for (const c of cs) {
    if (c.k === cur.k) continue
    const p = (c.x - cur.x) * dx + (c.y - cur.y) * dy
    if (p <= 4) continue
    const o = Math.abs((c.x - cur.x) * dy) + Math.abs((c.y - cur.y) * dx)
    const s = p + o * 2.2
    if (!mejor || s < mejor.s) mejor = { k: c.k, s }
  }
  if (mejor) elegirTeclado(mejor.k)
}
function elegirTeclado(k: string) {
  sel.value = null
  elegir(k)
  if (full.value) centrarEn([k])
}

function onKey(e: KeyboardEvent) {
  const el = e.target as HTMLElement | null
  if (e.metaKey || e.ctrlKey || e.altKey || el?.closest('input, textarea, select, [contenteditable]')) return
  const enBoton = !!el?.closest('button')
  const k = e.key
  if (k === 'Escape') {
    if (sel.value) cerrarDetalle()
    else if (andando.value) salirRecorrido()
    else if (full.value) setFull(false)
    else return
  } else if (k === 'ArrowRight') andando.value ? siguiente() : mover(1, 0)
  else if (k === 'ArrowLeft') andando.value ? anterior() : mover(-1, 0)
  else if (k === 'ArrowDown' && !andando.value) mover(0, 1)
  else if (k === 'ArrowUp' && !andando.value) mover(0, -1)
  else if (k === ' ' && andando.value && !enBoton) alternar()
  else if ((k === 'f' || k === 'F') && !enBoton) setFull(!full.value)
  else if ((k === '+' || k === '=') && full.value) zoomEn(1.25)
  else if ((k === '-' || k === '_') && full.value) zoomEn(0.8)
  else if (k === '0' && full.value) encajar(true)
  else return
  e.preventDefault()
  e.stopPropagation()
}
watch(full, (v) => {
  if (v) window.addEventListener('keydown', onKey, true)
  else window.removeEventListener('keydown', onKey, true)
})

/** Pans (full screen only) so the given things are in view. */
function centrarEn(keys: string[]) {
  if (!full.value) return
  const e = escena.value
  const cajas = keys.map((k) => e.nodos.find((n) => n.key === k) ?? e.aristas.find((a) => a.key === k)?.etiqueta).filter(Boolean) as { x: number; y: number; w: number; h: number }[]
  if (!cajas.length) return
  const x0 = Math.min(...cajas.map((c) => c.x)) * vista.z + vista.x
  const y0 = Math.min(...cajas.map((c) => c.y)) * vista.z + vista.y
  const x1 = Math.max(...cajas.map((c) => c.x + c.w)) * vista.z + vista.x
  const y1 = Math.max(...cajas.map((c) => c.y + c.h)) * vista.z + vista.y
  const m = 40
  if (x0 >= m && y0 >= m && x1 <= lw.value - m && y1 <= lh.value - m) return
  const fin = { x: vista.x + (lw.value / 2 - (x0 + x1) / 2), y: vista.y + (lh.value / 2 - (y0 + y1) / 2) }
  if (isSoft()) Object.assign(vista, fin)
  else run(() => gsap.to(vista, { ...fin, duration: 0.55, ease: 'power3.inOut', onUpdate: limitar }))
}

// ---------- guided walk (secuencia / proceso) ----------
const andando = ref(false)
const activo = ref(0)
const trail = ref<number[]>([0])
const playing = ref(false)
let reloj: gsap.core.Tween | null = null

/** Keys lit by each step, indexed like the diagram's steps. */
const pasosPorIndice = computed(() => {
  const f = conPasos.value
  if (!f) return []
  const out: string[][] = f.pasos.map(() => [])
  const orden = f.tipo === 'secuencia' ? f.pasos.map((_, i) => i) : ordenRecorrido(f)
  escena.value.pasos.forEach((ks, k) => {
    if (orden[k] !== undefined) out[orden[k]] = ks
  })
  return out
})
const largo = computed(() => (conPasos.value ? ruta(conPasos.value).length : 0))
const enRuta = computed(() => (conPasos.value && activo.value < conPasos.value.pasos.length ? ruta(conPasos.value).indexOf(activo.value) : -1))
const contador = computed(() => {
  const f = conPasos.value
  if (!f) return ''
  if (activo.value >= f.pasos.length) return 'Fin'
  return enRuta.value >= 0 ? `${enRuta.value + 1} / ${largo.value}` : `Paso ${numeroPaso(f, activo.value)}`
})
const anuncio = computed(() => {
  const f = conPasos.value
  if (!f || !andando.value) return ''
  if (activo.value >= f.pasos.length) return 'Terminó el recorrido'
  const p = f.pasos[activo.value]
  const quien = f.tipo === 'secuencia' ? `${f.actores[p.de].nombre}${p.de === p.a ? '' : ` a ${f.actores[p.a].nombre}`}. ` : ''
  return `Paso ${numeroPaso(f, activo.value)}. ${quien}${p.texto}. ${p.detalle}${p.decision ? ` ${p.decision.pregunta}` : ''}`
})

function lectura(i: number) {
  const p = conPasos.value!.pasos[i]
  return 1.6 + Math.min(3.6, (p.texto.length + p.detalle.length * 0.5) / 34)
}

function programar() {
  reloj?.kill()
  reloj = null
  if (!playing.value || !conPasos.value || activo.value >= conPasos.value.pasos.length) return
  reloj = gsap.delayedCall(lectura(activo.value), () => {
    if (playing.value) avanzar()
  })
}

function irAPaso(i: number, desde = activo.value) {
  const f = conPasos.value
  if (!f) return
  const de = desde
  activo.value = i
  if (i < f.pasos.length) {
    const at = trail.value.indexOf(i)
    if (at >= 0) trail.value.splice(at + 1)
    else trail.value.push(i)
  }
  nextTick(() => {
    recuadro.value?.entrar(de === i ? undefined : de, i, isSoft())
    centrarEn(pasosPorIndice.value[i] ?? [])
  })
  programar()
}

function avanzar() {
  const f = conPasos.value
  if (!f) return
  const n = nextOf(f, activo.value)
  if (n === null) {
    playing.value = false
    reloj?.kill()
    irAPaso(f.pasos.length)
    return
  }
  irAPaso(n)
}

function recorrer() {
  if (!conPasos.value) return
  haptic(8)
  cerrarDetalle()
  andando.value = true
  trail.value = [0]
  activo.value = 0
  playing.value = !isSoft()
  nextTick(() => {
    recuadro.value?.reveal()
    programar()
    centrarEn(pasosPorIndice.value[0] ?? [])
  })
}
function salirRecorrido() {
  playing.value = false
  reloj?.kill()
  reloj = null
  andando.value = false
}
function alternar() {
  haptic(8)
  playing.value = !playing.value
  if (playing.value && conPasos.value && activo.value >= conPasos.value.pasos.length) return reiniciar(true)
  programar()
}
function siguiente() {
  playing.value = false
  reloj?.kill()
  if (conPasos.value && activo.value < conPasos.value.pasos.length) avanzar()
}
function anterior() {
  playing.value = false
  reloj?.kill()
  const f = conPasos.value
  if (!f) return
  if (activo.value >= f.pasos.length) return irAPaso(trail.value[trail.value.length - 1] ?? 0)
  if (trail.value.length < 2) return
  trail.value.pop()
  irAPaso(trail.value[trail.value.length - 1])
}
function reiniciar(seguir = false) {
  playing.value = seguir
  trail.value = [0]
  irAPaso(0)
}
function elegirRama(a: number) {
  playing.value = false
  haptic(10)
  irAPaso(a)
}

// ---------- library ----------
function abrirBiblioteca() {
  if (!props.libId) return
  setFull(false)
  openInLibrary(props.libId)
}

// ---------- lifecycle ----------
function medir() {
  const el = lienzo.value
  if (!el) return
  lw.value = el.clientWidth
  lh.value = el.clientHeight
}

let ro: ResizeObserver | null = null
let io: IntersectionObserver | null = null
let entro = false
watch(escena, () => {
  if (full.value) nextTick(() => encajar())
  // a re-layout mid-entrance would leave new pieces half drawn: land on the final state instead
  if (entro) nextTick(() => dib.value?.mostrar())
})
watch(lw, (w, antes) => {
  if (full.value && antes && Math.abs(w - antes) > 1) encajar()
})

onMounted(() => {
  medir()
  if (lienzo.value) {
    ro = new ResizeObserver(medir)
    ro.observe(lienzo.value)
  }
  if (props.mini) return
  const animar = !props.quiet
  if (animar) dib.value?.ocultar()
  const visible = (v: boolean) => {
    if (v && !entro) {
      entro = true
      if (animar) dib.value?.entrar(isSoft())
    }
    dib.value?.pulsar(v && !isSoft())
  }
  if (typeof IntersectionObserver === 'undefined') visible(true)
  else {
    io = new IntersectionObserver((es) => visible(es.some((x) => x.isIntersecting)), { threshold: 0.15 })
    if (root.value) io.observe(root.value)
  }
})
onBeforeUnmount(() => {
  ro?.disconnect()
  io?.disconnect()
  reloj?.kill()
  window.removeEventListener('keydown', onKey, true)
  window.removeEventListener('pointermove', onMove)
  window.removeEventListener('pointerup', onUp)
  window.removeEventListener('pointercancel', onUp)
  if (full.value) document.body.style.overflow = ''
})

const lista = computed(() =>
  escena.value.nodos.map((n) => {
    const sale = escena.value.aristas.filter((a) => a.de === n.key && !a.propia).map((a) => `${escena.value.nodos.find((x) => x.key === a.a)?.nombre ?? ''}${a.titulo ? ` (${a.titulo})` : ''}`)
    return `${n.nombre}${n.tipoTexto ? `, ${n.tipoTexto.toLowerCase()}` : ''}. ${n.detalle}${sale.length ? ` Va a: ${sale.join(', ')}.` : ''}`
  }),
)
</script>

<template>
  <div class="holder" :style="full ? { minHeight: `${holderH}px` } : undefined">
    <Teleport to="body" :disabled="!full">
      <section
        ref="root"
        class="dc"
        :class="{ full, mini, andando }"
        :tabindex="mini ? -1 : 0"
        :aria-label="`${etiquetaTipo}: ${titulo}`"
        :style="{ '--rec-max': full ? 'min(40dvh, 320px)' : '230px' }"
        @keydown="!full && onKey($event)"
        @pointerdown="!mini && root?.focus({ preventScroll: true })"
      >
        <header v-if="!mini" class="hd">
          <span class="badge" aria-hidden="true"><Icon name="diagrama" :size="16" /></span>
          <div class="ttl">
            <span class="kind mono">{{ etiquetaTipo }}</span>
            <h3>{{ titulo }}</h3>
            <p v-if="resumen">{{ resumen }}</p>
          </div>
          <div class="acc">
            <button v-if="conPasos && !andando" type="button" class="rec-b" title="Recorrer paso a paso" @click="recorrer"><Icon name="play" :size="13" /><span>Recorrer</span></button>
            <button v-if="libId" type="button" class="ib" aria-label="Abrir en Biblioteca" title="Abrir en Biblioteca" @click="abrirBiblioteca"><Icon name="library" :size="16" /></button>
            <button type="button" class="ib" :aria-label="full ? 'Salir de pantalla completa' : 'Pantalla completa'" :title="full ? 'Salir (Esc)' : 'Pantalla completa (F)'" @click="setFull(!full)">
              <Transition name="icon-swap" mode="out-in"><Icon :key="full ? 'shrink' : 'expand'" :name="full ? 'shrink' : 'expand'" :size="16" /></Transition>
            </button>
          </div>
        </header>

        <div class="cuerpo">
          <div
            ref="lienzo"
            class="lienzo"
            @pointerdown="onDown"
            @wheel="onWheel"
            @dblclick="full && encajar(true)"
          >
            <div class="mover" :style="full ? { transform: `translate3d(${vista.x}px, ${vista.y}px, 0)` } : undefined">
              <DiagramaSvg
                ref="dib"
                :escena="escena"
                :foco="foco"
                :sel="sel"
                :titulo="titulo"
                :ancho="full ? escena.w * vista.z : escena.w * escala"
                :alto="full ? escena.h * vista.z : escena.h * escala"
                :estatico="mini"
                @tocar="elegir"
                @sobre="(k) => finePointer() && (sobre = k)"
              />
            </div>
            <div v-if="full" class="zoom">
              <button type="button" class="ib" aria-label="Alejar" title="Alejar (−)" @click="zoomEn(0.8)"><Icon name="minus" :size="16" /></button>
              <button type="button" class="pct mono" title="Encajar (0)" @click="encajar(true)">{{ Math.round(vista.z * 100) }}%</button>
              <button type="button" class="ib" aria-label="Acercar" title="Acercar (+)" @click="zoomEn(1.25)"><Icon name="plus" :size="16" /></button>
            </div>
          </div>

          <div v-if="andando && conPasos" class="walk">
            <div class="ctl">
              <button type="button" class="ib" aria-label="Paso anterior" title="Anterior (←)" :disabled="trail.length < 2 && activo < conPasos.pasos.length" @click="anterior"><Icon name="prev" :size="16" /></button>
              <button type="button" class="play" :aria-label="playing ? 'Pausar' : 'Reproducir'" :title="playing ? 'Pausar (Espacio)' : 'Reproducir (Espacio)'" @click="alternar">
                <Transition name="icon-swap" mode="out-in"><Icon :key="playing ? 'pause' : 'play'" :name="playing ? 'pause' : 'play'" :size="17" /></Transition>
              </button>
              <button type="button" class="ib" aria-label="Paso siguiente" title="Siguiente (→)" :disabled="activo >= conPasos.pasos.length" @click="siguiente"><Icon name="next" :size="16" /></button>
              <span class="cnt mono">{{ contador }}</span>
              <button type="button" class="salir" title="Ver el diagrama completo (Esc)" @click="salirRecorrido">Ver todo</button>
            </div>
            <PasosRecuadro ref="recuadro" :diagrama="conPasos" :activo="activo" :playing="playing" @elegir="elegirRama" @reiniciar="reiniciar(true)" />
          </div>
        </div>

        <ul v-if="notas.length && !mini && !andando" class="notas">
          <li v-for="(n, i) in notas" :key="i">{{ n }}</li>
        </ul>
        <button v-if="chico" type="button" class="ampliar" @click="setFull(true)"><Icon name="expand" :size="13" /> Ampliar para leer mejor</button>

        <Transition name="pop">
          <div v-if="info && pop && !hoja" ref="popEl" class="pop" role="dialog" :aria-label="info.titulo" :style="{ left: `${pop.left}px`, top: `${pop.top}px`, width: `${pop.w}px` }" @pointerdown.stop>
            <div class="det">
              <div class="det-hd">
                <span v-if="info.icono" class="det-ic">{{ info.icono }}</span>
                <div class="det-tt">
                  <span v-if="info.chip" class="det-chip mono">{{ info.chip }}</span>
                  <b>{{ info.titulo }}</b>
                </div>
                <button type="button" class="ib sm" aria-label="Cerrar" @click="cerrarDetalle"><Icon name="close" :size="14" /></button>
              </div>
              <p v-if="info.sub" class="det-sub mono">{{ info.sub }}</p>
              <p v-if="info.detalle" class="det-tx">{{ info.detalle }}</p>
              <p v-if="info.datos" class="det-datos mono">{{ info.datos }}</p>
              <ul v-if="info.enlaces.length" class="det-en">
                <li v-for="(l, i) in info.enlaces" :key="i">
                  <button type="button" @click="elegir(l.key)">
                    <span class="dir" :class="{ sale: l.sale }">{{ l.num || (l.sale ? '→' : '←') }}</span>
                    <span class="en-tx"><b>{{ l.otro }}</b><template v-if="l.texto"> · {{ l.texto }}</template></span>
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </Transition>

        <p class="sr" aria-live="polite">{{ anuncio }}</p>
        <ol v-if="!mini" class="sr" :aria-label="`Contenido del ${etiquetaTipo.toLowerCase()}`">
          <template v-if="conPasos">
            <li v-for="(p, i) in conPasos.pasos" :key="i">
              <template v-if="conPasos.tipo === 'secuencia'">{{ conPasos.actores[p.de].nombre }}{{ p.de === p.a ? '' : ` a ${conPasos.actores[p.a].nombre}` }}: </template>{{ p.texto }}. {{ p.detalle }} {{ p.decision ? p.decision.pregunta : '' }}
            </li>
          </template>
          <li v-for="(t, i) in conPasos ? [] : lista" v-else :key="`n${i}`">{{ t }}</li>
        </ol>
      </section>
    </Teleport>

    <Teleport to="body">
      <Transition name="hoja">
        <div v-if="hoja && info" class="velo" @click="cerrarDetalle">
          <div class="hoja" role="dialog" :aria-label="info.titulo" @click.stop>
            <i class="grip" aria-hidden="true" />
            <div class="det">
              <div class="det-hd">
                <span v-if="info.icono" class="det-ic">{{ info.icono }}</span>
                <div class="det-tt">
                  <span v-if="info.chip" class="det-chip mono">{{ info.chip }}</span>
                  <b>{{ info.titulo }}</b>
                </div>
                <button type="button" class="ib" aria-label="Cerrar" @click="cerrarDetalle"><Icon name="close" :size="16" /></button>
              </div>
              <p v-if="info.sub" class="det-sub mono">{{ info.sub }}</p>
              <p v-if="info.detalle" class="det-tx">{{ info.detalle }}</p>
              <p v-else-if="!info.enlaces.length" class="det-tx muted">Sin más detalle.</p>
              <p v-if="info.datos" class="det-datos mono">{{ info.datos }}</p>
              <ul v-if="info.enlaces.length" class="det-en">
                <li v-for="(l, i) in info.enlaces" :key="i">
                  <button type="button" @click="elegir(l.key)">
                    <span class="dir" :class="{ sale: l.sale }">{{ l.num || (l.sale ? '→' : '←') }}</span>
                    <span class="en-tx"><b>{{ l.otro }}</b><template v-if="l.texto"> · {{ l.texto }}</template></span>
                  </button>
                </li>
              </ul>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.holder {
  width: 100%;
  min-width: 0;
}
.dc {
  --tx: 17px;
  --dt: 14px;
  position: relative;
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  margin: 12px 0 6px;
  padding: 14px 12px 12px;
  border-radius: 18px;
  background:
    radial-gradient(120% 70% at 0% 0%, var(--accent-soft), transparent 55%),
    var(--surface);
  border: 1px solid var(--line-2);
  box-shadow: var(--shadow-pop);
  outline: none;
  min-width: 0;
}
.dc:focus-visible {
  border-color: var(--accent-line);
}
.dc.mini {
  margin: 0;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: none;
  box-shadow: none;
  height: 100%;
}
.hd {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}
.badge {
  flex: none;
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: var(--r-md);
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.ttl {
  flex: 1;
  min-width: 0;
}
.kind {
  display: block;
  font-size: 10px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
}
.ttl h3 {
  margin: 1px 0 0;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  line-height: 1.25;
  letter-spacing: -0.01em;
  overflow-wrap: anywhere;
}
.ttl p {
  margin: 3px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.dc:not(.full) .ttl p {
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  overflow: hidden;
}
.acc {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
}
.ib {
  flex: none;
  display: grid;
  place-items: center;
  width: 40px;
  height: 40px;
  border-radius: 12px;
  color: var(--text-2);
  transition: background 0.2s, color 0.2s, opacity 0.2s, scale 0.3s var(--spring);
}
.ib.sm {
  width: 30px;
  height: 30px;
  border-radius: var(--r-md);
}
.ib:disabled {
  opacity: 0.35;
  cursor: default;
}
.ib:not(:disabled):active {
  scale: var(--press-scale);
}
@media (hover: hover) {
  .ib:not(:disabled):hover {
    color: var(--text);
    background: var(--surface-hover);
  }
}
.rec-b {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  margin-right: 4px;
  padding: 0 12px 0 10px;
  border-radius: var(--r-pill);
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, color 0.2s, box-shadow 0.2s, scale 0.3s var(--spring);
}
.rec-b:active {
  scale: var(--press-scale);
}
@media (hover: hover) {
  .rec-b:hover {
    color: var(--accent);
    box-shadow: inset 0 0 0 1px var(--accent-line);
    background: var(--accent-soft);
  }
}
@media (max-width: 420px) {
  .rec-b span {
    display: none;
  }
  .rec-b {
    width: 40px;
    height: 40px;
    padding: 0;
    margin: 0;
    justify-content: center;
    box-shadow: none;
    border-radius: 12px;
  }
}

.cuerpo {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 12px;
  min-width: 0;
  min-height: 0;
}
.lienzo {
  position: relative;
  min-width: 0;
  display: flex;
  justify-content: center;
  padding: 4px 0;
}
.dc.mini .cuerpo,
.dc.mini .lienzo {
  height: 100%;
  align-items: center;
  padding: 0;
}
.mover {
  min-width: 0;
}

.walk {
  display: grid;
  gap: 10px;
  align-content: start;
  min-width: 0;
}
.ctl {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
}
.play {
  flex: none;
  display: grid;
  place-items: center;
  width: 50px;
  height: 40px;
  margin: 0 2px;
  border-radius: var(--r-lg);
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: 0 10px 26px -12px var(--accent);
  transition: scale 0.35s var(--spring);
}
.play:active {
  scale: var(--press-scale);
}
.cnt {
  margin-left: 6px;
  font-size: 12px;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.salir {
  margin-left: auto;
  height: 34px;
  padding: 0 12px;
  border-radius: var(--r-pill);
  font-size: var(--t-md);
  font-weight: 600;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  white-space: nowrap;
}
@media (hover: hover) {
  .salir:hover {
    color: var(--text);
    background: var(--surface-hover);
  }
}

.notas {
  margin: 0;
  padding: 0 4px;
  list-style: none;
  display: grid;
  gap: 4px;
}
.notas li {
  position: relative;
  padding-left: 14px;
  font-size: var(--t-md);
  line-height: 1.45;
  color: var(--text-3);
}
.notas li::before {
  content: '';
  position: absolute;
  left: 2px;
  top: 0.62em;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
  opacity: 0.7;
}
.ampliar {
  justify-self: center;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 32px;
  padding: 0 14px;
  border-radius: var(--r-pill);
  font-size: 12px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}

/* detail */
.pop {
  position: absolute;
  z-index: 5;
  padding: 14px 14px 12px;
  border-radius: 16px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  box-shadow: var(--shadow-pop), 0 24px 48px -24px rgba(0, 0, 0, 0.5);
}
.pop-enter-active,
.pop-leave-active {
  transition: opacity 0.2s, transform 0.3s var(--spring);
}
.pop-enter-from,
.pop-leave-to {
  opacity: 0;
  transform: translateY(6px) scale(0.97);
}
.det {
  display: grid;
  gap: 8px;
  min-width: 0;
}
.det-hd {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}
.det-ic {
  flex: none;
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--r-md);
  font-size: 19px;
  background: var(--surface-2);
}
.det-tt {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}
.det-chip {
  font-size: var(--t-xs);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--accent);
  overflow-wrap: anywhere;
}
.det-tt b {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.3;
  overflow-wrap: anywhere;
}
.det-sub {
  margin: 0;
  font-size: 12px;
  color: var(--text-3);
}
.det-tx {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
.det-tx.muted {
  color: var(--text-4);
}
.det-datos {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--r-md);
  font-size: 12px;
  color: var(--text-2);
  background: var(--code-bg);
  overflow-wrap: anywhere;
}
.det-en {
  margin: 2px 0 0;
  padding: 8px 0 0;
  list-style: none;
  display: grid;
  gap: 2px;
  border-top: 1px solid var(--line);
}
.det-en button {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  width: 100%;
  padding: 6px 6px;
  border-radius: var(--r-md);
  text-align: left;
  font-size: 13px;
  line-height: 1.4;
  color: var(--text-2);
}
@media (hover: hover) {
  .det-en button:hover {
    background: var(--surface-hover);
    color: var(--text);
  }
}
.dir {
  flex: none;
  display: grid;
  place-items: center;
  min-width: 20px;
  height: 20px;
  padding: 0 4px;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-3);
  background: var(--surface-2);
}
.dir.sale {
  color: var(--accent);
  background: var(--accent-soft);
}
.en-tx {
  min-width: 0;
  overflow-wrap: anywhere;
}
.en-tx b {
  font-weight: 600;
  color: var(--text);
}

.velo {
  position: fixed;
  inset: 0;
  z-index: 400;
  display: flex;
  align-items: flex-end;
  justify-content: center;
  background: rgba(0, 0, 0, 0.28);
}
.hoja {
  position: relative;
  width: 100%;
  max-width: 560px;
  max-height: 70dvh;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 22px 18px max(18px, env(safe-area-inset-bottom));
  border-radius: 22px 22px 0 0;
  background: var(--surface);
  border-top: 1px solid var(--line-2);
  box-shadow: 0 -20px 50px -20px rgba(0, 0, 0, 0.55);
}
.grip {
  position: absolute;
  top: 8px;
  left: 50%;
  width: 38px;
  height: 4px;
  margin-left: -19px;
  border-radius: 99px;
  background: var(--line-2);
}
.hoja .det-tt b {
  font-size: 17px;
}
.hoja .det-tx {
  font-size: 15px;
}
.hoja-enter-active,
.hoja-leave-active {
  transition: background 0.3s;
}
.hoja-enter-active .hoja,
.hoja-leave-active .hoja {
  transition: transform 0.42s var(--spring);
}
.hoja-leave-active .hoja {
  transition-duration: 0.25s;
  transition-timing-function: ease-in;
}
.hoja-enter-from,
.hoja-leave-to {
  background: transparent;
}
.hoja-enter-from .hoja,
.hoja-leave-to .hoja {
  transform: translateY(100%);
}
:root[data-motion='soft'] .hoja-enter-active .hoja,
:root[data-motion='soft'] .hoja-leave-active .hoja {
  transition: opacity 0.2s;
  transform: none;
}

.sr {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  padding: 0;
  overflow: hidden;
  clip-path: inset(50%);
  white-space: nowrap;
}

/* full screen */
.dc.full {
  position: fixed;
  inset: 0;
  z-index: 300;
  margin: 0;
  padding: max(14px, env(safe-area-inset-top)) max(14px, env(safe-area-inset-right)) max(14px, env(safe-area-inset-bottom)) max(14px, env(safe-area-inset-left));
  border: 0;
  border-radius: 0;
  background:
    radial-gradient(90% 60% at 0% 0%, var(--accent-soft), transparent 50%),
    var(--bg);
  box-shadow: none;
  overflow: hidden;
  grid-template-rows: auto minmax(0, 1fr) auto;
}
.dc.full .cuerpo {
  grid-template-rows: minmax(0, 1fr);
}
.dc.full.andando .cuerpo {
  grid-template-rows: minmax(0, 1fr) auto;
}
.dc.full .lienzo {
  display: block;
  padding: 0;
  overflow: hidden;
  touch-action: none;
  cursor: grab;
  border-radius: 16px;
  background-image: radial-gradient(circle, var(--line) 1px, transparent 1.2px);
  background-size: 22px 22px;
}
.dc.full .lienzo:active {
  cursor: grabbing;
}
.dc.full .mover {
  position: absolute;
  top: 0;
  left: 0;
  transform-origin: 0 0;
  will-change: transform;
}
.dc.full .ttl h3 {
  font-size: 20px;
}
.zoom {
  position: absolute;
  right: 12px;
  bottom: 12px;
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 3px;
  border-radius: var(--r-lg);
  background: var(--surface);
  border: 1px solid var(--line-2);
  box-shadow: var(--shadow-pop);
}
.pct {
  min-width: 52px;
  height: 36px;
  border-radius: var(--r-md);
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
  font-variant-numeric: tabular-nums;
}
@media (hover: hover) {
  .pct:hover {
    background: var(--surface-hover);
    color: var(--text);
  }
}
@media (min-width: 900px) {
  .dc.full {
    padding-left: max(28px, env(safe-area-inset-left));
    padding-right: max(28px, env(safe-area-inset-right));
  }
  .dc.full.andando .cuerpo {
    grid-template-columns: minmax(0, 1fr) clamp(320px, 30%, 400px);
    grid-template-rows: minmax(0, 1fr);
    column-gap: 18px;
  }
  .dc.full.andando .walk {
    align-self: center;
  }
  .dc.full {
    --rec-max: 56dvh;
    --tx: 22px;
    --dt: 16px;
  }
}
</style>
