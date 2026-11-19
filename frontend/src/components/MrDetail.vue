<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { PIPE_LABEL, type MrJob, type MrPersona } from '../api/mrsApi'
import { elegidosDesdeReviewers, reviewersParaGuardar } from '../lib/mrReviewers'
import { mrDetailEscapeAllowed } from '../lib/mrDetailEscape'
import { agruparActividad, gitlabCtx, renderGitlabMarkdown } from '../lib/gitlabMarkdown'
import { ago, fechaLarga, useNow } from '../lib/time'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { aprobar, cambiarReviewers, cargarDetalle, comentar, envio, mandarASesion, marcarDraft, mrSel, mrs, mrsApi, mrsPin, mrsVisible, pausar, pedirActualizacion, pedirPin, reintentar, sesionDeMr, type Accion } from '../state/mrs'
import CopyBtn from './CopyBtn.vue'
import Icon from './Icon.vue'
import InlineAlert from './InlineAlert.vue'
import SkeletonList from './SkeletonList.vue'
import MrPipe from './MrPipe.vue'
import MrDestinoSheet from './MrDestinoSheet.vue'

const emit = defineEmits<{ back: [] }>()
const { run } = useGsap()
const now = useNow()
const root = ref<HTMLElement | null>(null)

const d = computed(() => (mrs.detalle?.ref === mrs.sel ? mrs.detalle : null))
const m = computed(() => d.value ?? mrSel.value)
const esAutor = computed(() => m.value?.rol === 'autor')
const ctx = computed(() => gitlabCtx(m.value?.url))
const html = computed(() => renderGitlabMarkdown(d.value?.descripcion ?? '', ctx.value))
const notasHtml = computed(() => {
  const map: Record<string, string> = {}
  for (const h of d.value?.hilos ?? []) {
    for (const n of h.notas) map[n.id] = renderGitlabMarkdown(n.cuerpo, ctx.value)
  }
  return map
})
const actividad = computed(() => agruparActividad(d.value?.actividad ?? []))
const ACTIVIDAD_VISIBLE = 4
const verActividad = ref(false)
const actividadVisible = computed(() => (verActividad.value ? actividad.value : actividad.value.slice(-ACTIVIDAD_VISIBLE)))

const etapas = computed(() => {
  const out: { etapa: string; jobs: MrJob[] }[] = []
  for (const j of d.value?.jobs ?? []) {
    const last = out[out.length - 1]
    if (last && last.etapa === j.etapa) last.jobs.push(j)
    else out.push({ etapa: j.etapa, jobs: [j] })
  }
  return out
})
const hilos = computed(() => [...(d.value?.hilos ?? [])].sort((a, b) => Number(a.resuelto) - Number(b.resuelto)))
const abiertos = ref(new Set<string>())
const toggleArchivo = (p: string) => {
  const s = new Set(abiertos.value)
  if (!s.delete(p)) s.add(p)
  abiertos.value = s
}
const lineas = (diff: string) => diff.split('\n').map((t) => ({ t, k: t.startsWith('@@') ? 'hunk' : t.startsWith('+') ? 'add' : t.startsWith('-') ? 'del' : '' }))
const dur = (s: number) => (!s ? '' : s < 60 ? `${s} s` : `${Math.floor(s / 60)} min ${s % 60 ? `${s % 60} s` : ''}`.trim())

interface Pendiente {
  id: Accion
  texto: string
  cta: string
  danger?: boolean
  go: () => Promise<boolean>
}
const pendiente = ref<Pendiente | null>(null)
function pedir(p: Pendiente) {
  haptic(6)
  mrs.errConfirm = ''
  pendiente.value = p
}
async function confirmar() {
  const p = pendiente.value
  if (!p || mrs.busy) return
  haptic([8, 30, 8])
  const ok = await p.go()
  if (ok && pendiente.value === p) pendiente.value = null
}

const ref_ = computed(() => m.value?.ref ?? '')
const nombre = computed(() => (m.value ? `!${m.value.iid}` : ''))

function pedirAprobar() {
  const si = !m.value?.aprobaciones.yo
  pedir({ id: si ? 'aprobar' : 'desaprobar', texto: si ? `¿Aprobar ${nombre.value}?` : `¿Sacar tu aprobación de ${nombre.value}?`, cta: si ? 'Aprobar' : 'Sacar aprobación', go: () => aprobar(ref_.value, si) })
}
const sesion = computed(() => (m.value ? sesionDeMr(m.value.ref) : null))
function pedirASesion() {
  pedir({
    id: 'pedir',
    texto: `Le mando a la sesión de ${nombre.value}: «Actualizá el MR con los últimos cambios de la rama: push y descripción si hace falta. Avisame antes del push.»`,
    cta: 'Pedirle a la sesión',
    go: () => pedirActualizacion(ref_.value),
  })
}
function pedirDraft() {
  const draft = !m.value?.draft
  pedir({ id: draft ? 'draft' : 'listo', texto: draft ? `¿Volver ${nombre.value} a draft?` : `¿Marcar ${nombre.value} como listo para revisar?`, cta: draft ? 'Pasar a draft' : 'Marcar listo', go: () => marcarDraft(ref_.value, draft) })
}
function pedirReintentoPipeline() {
  const id = d.value?.pipeline.id
  if (!id) return
  pedir({ id: 'reintentar', texto: 'Se vuelven a correr los jobs que fallaron del pipeline.', cta: 'Reintentar pipeline', go: () => reintentar(ref_.value, { pipeline_id: id }) })
}
function pedirReintentoJob(j: MrJob) {
  pedir({ id: 'reintentar', texto: `¿Reintentar el job ${j.nombre}?`, cta: 'Reintentar job', go: () => reintentar(ref_.value, { job_id: j.id }) })
}

const texto = ref('')
function pedirComentario() {
  const t = texto.value.trim()
  if (!t) return
  pedir({
    id: 'comentar',
    texto: `Se publica tu comentario en ${nombre.value}, lo ve todo el equipo.`,
    cta: 'Publicar',
    go: async () => {
      const ok = await comentar(ref_.value, t)
      if (ok) texto.value = ''
      return ok
    },
  })
}

const editando = ref(false)
const elegidos = ref(new Set<string>())
const equipo = ref<MrPersona[]>([])
const equipoListo = ref(false)

async function cargarEquipo() {
  if (equipoListo.value || !mrs.habilitado) return
  try {
    const o = await mrsApi().opciones()
    equipo.value = o.equipo ?? []
  } catch {
    equipo.value = []
  } finally {
    equipoListo.value = true
  }
}

// El equipo se pide recién al tocar «Cambiar»: leerlo al abrir cada MR recorría los repos locales de más.

const puedeGuardarReviewers = computed(
  () => reviewersParaGuardar(equipo.value, elegidos.value, equipoListo.value) !== null,
)

async function editarReviewers() {
  editando.value = true
  // Sin equipo cargado la selección saldría vacía y guardar borraría los reviewers.
  await cargarEquipo()
  elegidos.value = elegidosDesdeReviewers(m.value?.reviewers ?? [], equipo.value)
}
function toggleReviewer(u: string) {
  haptic(4)
  const s = new Set(elegidos.value)
  if (!s.delete(u)) s.add(u)
  elegidos.value = s
}
function pedirReviewers() {
  const lista = reviewersParaGuardar(equipo.value, elegidos.value, equipoListo.value)
  if (lista === null) return
  const nombres = equipo.value.filter((e) => elegidos.value.has(e.username)).map((e) => e.nombre.split(' ')[0])
  pedir({
    id: 'reviewers',
    texto: lista.length ? `Reviewers: ${nombres.join(', ')}.` : 'El MR queda sin reviewers.',
    cta: 'Guardar reviewers',
    go: async () => {
      const ok = await cambiarReviewers(ref_.value, lista)
      if (ok) editando.value = false
      return ok
    },
  })
}

const motivoNoMerge = computed(() => {
  const x = m.value
  if (!x) return ''
  if (x.draft) return 'Es draft'
  if (x.conflictos) return 'Tiene conflictos'
  if (x.pipeline.estado === 'fallo') return 'El pipeline falló'
  if (x.aprobaciones.faltan > 0) return x.aprobaciones.faltan === 1 ? 'Falta una aprobación' : `Faltan ${x.aprobaciones.faltan} aprobaciones`
  if (!x.puede_mergear) return 'GitLab todavía no lo deja mergear'
  return ''
})

function onKey(e: KeyboardEvent) {
  if (!mrDetailEscapeAllowed(mrsVisible.value, mrsPin.open, e.key, e.defaultPrevented)) return
  if (document.querySelector('[aria-modal="true"]')) return
  const t = e.target as HTMLElement | null
  if (t?.closest?.('textarea, input, select, [contenteditable="true"]')) return
  if (pendiente.value) {
    if (!mrs.busy) pendiente.value = null
  } else if (editando.value) editando.value = false
  else emit('back')
  e.preventDefault()
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

watch(
  () => d.value?.ref,
  async (r, o) => {
    if (!r || r === o || isSoft()) return
    await nextTick()
    const blocks = root.value?.querySelectorAll('.blk')
    if (blocks?.length) run(() => gsap.from(blocks, { y: 14, opacity: 0, duration: 0.5, ease: 'power3.out', stagger: 0.05, clearProps: 'transform,opacity' }))
  },
)

function barEnter(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.15, onComplete: done }))
  run(() => gsap.fromTo(el, { y: 24, opacity: 0, scale: 0.97 }, { y: 0, opacity: 1, scale: 1, duration: 0.45, ease: 'back.out(1.6)', clearProps: 'transform', onComplete: done }))
}
function barLeave(el: Element, done: () => void) {
  if (isSoft()) return void run(() => gsap.to(el, { opacity: 0, duration: 0.12, onComplete: done }))
  run(() => gsap.to(el, { y: 18, opacity: 0, duration: 0.2, ease: 'power2.in', onComplete: done }))
}
</script>

<template>
  <article v-if="m" ref="root" class="det" :aria-label="`MR ${nombre}`">
    <div class="bar">
      <button class="back" aria-label="Volver a la lista" @click="emit('back')"><Icon name="back" :size="19" /></button>
      <span class="repo">{{ m.repo_corto }} <b class="mono">{{ nombre }}</b></span>
      <CopyBtn v-if="m.url" icon class="ext" :text="m.url" label="Copiar link del MR" />
    </div>
    <div class="scroll">
      <header class="hd">
        <h2>{{ m.titulo }}</h2>
        <p class="ramas mono"><Icon name="branch" :size="13" /> <span>{{ m.rama }}</span> <i>→</i> <span>{{ m.target }}</span></p>
        <div class="badges">
          <MrPipe :estado="m.pipeline.estado" :label="PIPE_LABEL[m.pipeline.estado]" />
          <button v-if="esAutor" class="b btn-b" :class="{ on: m.draft }" :disabled="!!mrs.busy" @click="pedirDraft">{{ m.draft ? 'Draft · marcar listo' : 'Pasar a draft' }}</button>
          <i v-else-if="m.draft" class="b">Draft</i>
          <button
            class="b btn-b"
            :class="{ on: m.pausado }"
            :disabled="!!mrs.busy"
            title="Lo saca de la lista y del aviso hasta que haya movimiento nuevo"
            @click="void pausar(m.ref, !m.pausado); mrs.errConfirm = ''"
          >
            <Transition name="icon-swap" mode="out-in"><Icon :key="m.pausado ? 'play' : 'pause'" :name="m.pausado ? 'play' : 'pause'" :size="10" /></Transition> {{ m.pausado ? 'En pausa · sacar' : 'Pausar' }}
          </button>
          <p v-if="mrs.pausaErr" class="problem pausa-err" role="alert">{{ mrs.pausaErr }}</p>
          <i v-if="m.conflictos" class="b bad"><Icon name="warn" :size="12" /> Conflictos</i>
          <i v-if="m.rol === 'revisor'" class="b who">de {{ m.autor.nombre || m.autor.username }}</i>
          <i v-if="m.creado" class="b who">Creado el {{ fechaLarga(m.creado) }}</i>
          <i v-if="m.actualizado" class="b who">{{ ago(m.actualizado, now) }}</i>
        </div>
        <div v-if="sesion" class="a-sesion">
          <button class="chip" :disabled="!!mrs.busy" @click="pedirASesion"><Icon name="arrow-up" :size="13" /> Pedirle a la sesión que lo actualice</button>
          <p v-if="mrs.okMsg" class="ok-msg" role="status">{{ mrs.okMsg }}</p>
        </div>
      </header>

      <InlineAlert v-if="mrs.detError">
        {{ mrs.detError }}
        <template #action><button type="button" class="btn btn-link" @click="cargarDetalle(m.ref)">Reintentar</button></template>
      </InlineAlert>

      <SkeletonList v-if="!d && mrs.detLoading" :count="3" class="blk" />

      <template v-if="d">
        <section class="blk">
          <header class="bh">
            <h3>Pipeline</h3>
            <a v-if="d.pipeline.url" class="link" :href="d.pipeline.url" target="_blank" rel="noopener noreferrer">#{{ d.pipeline.id }}</a>
            <button v-if="d.pipeline.estado === 'fallo' && d.pipeline.id" class="chip" :disabled="!!mrs.busy" @click="pedirReintentoPipeline"><Icon name="refresh" :size="13" /> Reintentar pipeline</button>
          </header>
          <p v-if="!etapas.length" class="muted">{{ d.pipeline.estado === 'sin' ? 'Este MR no tiene pipeline.' : 'No hay jobs para mostrar.' }}</p>
          <div v-for="e in etapas" :key="e.etapa" class="etapa">
            <span class="et">{{ e.etapa }}</span>
            <ul class="jobs">
              <li v-for="j in e.jobs" :key="j.id" class="job" :class="[j.estado, { 'con-mandar': j.estado === 'fallo' || j.estado === 'cancelado' }]">
                <MrPipe :estado="j.estado" compact />
                <a v-if="j.url" class="jn" :href="j.url" target="_blank" rel="noopener noreferrer">{{ j.nombre }}</a>
                <span v-else class="jn">{{ j.nombre }}</span>
                <i v-if="j.permitido_fallar && j.estado === 'fallo'" class="b mini">puede fallar</i>
                <span class="jd mono">{{ dur(j.duracion) }}</span>
                <button v-if="j.reintentable && (j.estado === 'fallo' || j.estado === 'cancelado')" class="ib" :aria-label="`Reintentar ${j.nombre}`" :disabled="!!mrs.busy" @click="pedirReintentoJob(j)">
                  <Icon name="refresh" :size="14" />
                </button>
                <button
                  v-if="j.estado === 'fallo' || j.estado === 'cancelado'"
                  class="ib mandar hit"
                  :class="{ hecho: envio.hecho === `job:${j.id}` }"
                  :aria-label="`Mandar el job ${j.nombre} a la sesión`"
                  :title="envio.hecho === `job:${j.id}` ? 'Mandado' : 'Mandar el log a la sesión'"
                  :disabled="!!envio.cual"
                  @click="mandarASesion(ref_, { tipo: 'job', id: j.id })"
                >
                  <Icon :name="envio.hecho === `job:${j.id}` ? 'check' : 'arrow-up'" :size="14" />
                </button>
                <p v-if="envio.error.clave === `job:${j.id}`" class="mandar-err" role="alert">{{ envio.error.msg }}</p>
              </li>
            </ul>
          </div>
        </section>

        <section class="blk">
          <header class="bh">
            <h3>Aprobaciones</h3>
            <span class="count mono" :class="{ good: d.aprobaciones.faltan === 0 && d.aprobaciones.dadas > 0 }">{{ d.aprobaciones.dadas }}<template v-if="d.aprobaciones.requeridas">/{{ d.aprobaciones.requeridas }}</template></span>
          </header>
          <div class="people">
            <span v-for="p in d.aprobaciones.por" :key="p.username" class="person ok"><Icon name="check" :size="12" /> {{ p.nombre || p.username }}</span>
            <span v-if="!d.aprobaciones.por.length" class="muted">Todavía nadie aprobó.</span>
          </div>
          <div class="sub-h">
            <span>Reviewers</span>
            <button v-if="esAutor && !editando" class="link" @click="editarReviewers">Cambiar</button>
          </div>
          <div v-if="!editando" class="people">
            <span v-for="p in d.reviewers" :key="p.username" class="person">{{ p.nombre || p.username }}</span>
            <span v-if="!d.reviewers.length" class="muted">Sin reviewers.</span>
          </div>
          <div v-else class="pick">
            <button v-for="e in equipo" :key="e.username" class="person pickable" :class="{ on: elegidos.has(e.username) }" :aria-pressed="elegidos.has(e.username)" @click="toggleReviewer(e.username)">
              <Icon v-if="elegidos.has(e.username)" name="check" :size="12" /> {{ e.nombre }}
            </button>
            <p v-if="equipoListo && !equipo.length" class="muted">No hay equipo cargado todavía.</p>
            <div class="pick-act">
              <button class="chip" @click="editando = false">Cancelar</button>
              <button class="chip go" :disabled="!!mrs.busy || !puedeGuardarReviewers" @click="pedirReviewers">Guardar</button>
            </div>
          </div>
        </section>

        <section v-if="d.descripcion" class="blk">
          <header class="bh"><h3>Descripción</h3></header>
          <div class="md desc" v-html="html" />
        </section>

        <section class="blk">
          <header class="bh">
            <h3>Hilos</h3>
            <span v-if="d.hilos_sin_resolver" class="count bad mono">{{ d.hilos_sin_resolver }} sin resolver</span>
          </header>
          <p v-if="!hilos.length" class="muted">No hay comentarios.</p>
          <div v-for="h in hilos" :key="h.id" class="hilo" :class="{ res: h.resuelto, open: h.resoluble && !h.resuelto }">
            <p v-if="h.archivo" class="donde mono"><Icon name="doc" :size="12" /> {{ h.archivo }}<template v-if="h.linea">:{{ h.linea }}</template></p>
            <div v-for="n in h.notas" :key="n.id" class="nota" :class="{ mia: n.mio }">
              <span class="quien"><b>{{ n.mio ? 'Vos' : n.autor.nombre || n.autor.username }}</b> <i>{{ ago(n.fecha, now) }}</i></span>
              <div class="md cuerpo" v-html="notasHtml[n.id]" />
            </div>
            <span v-if="h.resuelto" class="resuelto"><Icon name="check" :size="12" /> Resuelto</span>
            <div v-else class="hilo-acc">
              <button
                class="chip hit"
                :aria-label="`Mandar el comentario${h.archivo ? ` de ${h.archivo}` : ''} a la sesión`"
                :disabled="!!envio.cual"
                @click="mandarASesion(ref_, { tipo: 'hilo', id: h.id })"
              >
                <Icon :name="envio.hecho === `hilo:${h.id}` ? 'check' : 'arrow-up'" :size="13" /> {{ envio.hecho === `hilo:${h.id}` ? 'Mandado' : 'Mandar a la sesión' }}
              </button>
              <p v-if="envio.error.clave === `hilo:${h.id}`" class="mandar-err" role="alert">{{ envio.error.msg }}</p>
            </div>
          </div>
          <div v-if="actividad.length" class="actividad" aria-label="Actividad del MR">
            <button v-if="actividad.length > ACTIVIDAD_VISIBLE" class="act-more" :aria-expanded="verActividad" @click="verActividad = !verActividad">
              <Icon name="chevron" :size="12" class="chev" :class="{ rot: verActividad }" />
              {{ verActividad ? 'Ver menos actividad' : `${actividad.length - ACTIVIDAD_VISIBLE} eventos anteriores` }}
            </button>
            <ol class="act-list">
              <li v-for="e in actividadVisible" :key="e.id" class="act">
                <i class="dot" aria-hidden="true" />
                <span class="act-t"><b>{{ e.quien }}</b> {{ e.texto }}<em v-if="e.veces > 1" class="veces"> ×{{ e.veces }}</em></span>
                <time v-if="e.fecha" class="act-f">{{ ago(e.fecha, now) }}</time>
              </li>
            </ol>
          </div>
          <form class="comentar" @submit.prevent="pedirComentario">
            <textarea v-model="texto" rows="2" maxlength="5000" placeholder="Escribí un comentario…" aria-label="Comentario" />
            <button class="chip go" type="submit" :disabled="!texto.trim() || !!mrs.busy"><Icon name="arrow-up" :size="13" /> Comentar</button>
          </form>
        </section>

        <section class="blk">
          <header class="bh">
            <h3>Archivos</h3>
            <span class="count mono">{{ d.archivos.length }}</span>
          </header>
          <ul class="files">
            <li v-for="f in d.archivos" :key="f.path" class="file">
              <button class="fh" :aria-expanded="abiertos.has(f.path)" :disabled="!f.diff" @click="toggleArchivo(f.path)">
                <i class="kind" :class="{ add: f.nuevo, del: f.borrado, mv: f.renombrado }">{{ f.nuevo ? 'A' : f.borrado ? 'D' : f.renombrado ? 'R' : 'M' }}</i>
                <span class="fp mono">{{ f.path }}</span>
                <Icon v-if="f.diff" name="chevron" :size="14" class="chev" :class="{ rot: abiertos.has(f.path) }" />
              </button>
              <div v-if="abiertos.has(f.path)" class="diff">
                <pre class="mono"><code><span v-for="(l, i) in lineas(f.diff)" :key="i" class="ln" :class="l.k">{{ l.t || ' ' }}
</span></code></pre>
                <p v-if="f.truncado" class="muted">Diff recortado: el resto está en GitLab.</p>
              </div>
            </li>
          </ul>
        </section>
      </template>
    </div>

    <footer class="acts">
      <Transition :css="false" mode="out-in" @enter="barEnter" @leave="barLeave">
        <div v-if="pendiente" key="conf" class="confirm" role="alertdialog" aria-live="polite">
          <p>{{ pendiente.texto }}</p>
          <p v-if="mrs.errConfirm" class="problem" role="alert">{{ mrs.errConfirm }}</p>
          <div class="row">
            <button class="btn ghost" :disabled="!!mrs.busy" @click="pendiente = null">Cancelar</button>
            <button class="btn go" :class="{ busy: mrs.busy === pendiente.id }" :disabled="!!mrs.busy" @click="confirmar">
              <span v-if="mrs.busy === pendiente.id" class="spin" aria-hidden="true" />{{ pendiente.cta }}
            </button>
          </div>
        </div>
        <div v-else key="main" class="row main-row">
          <button v-if="m.aprobaciones.puedo || m.aprobaciones.yo" class="btn" :class="m.aprobaciones.yo ? 'ghost' : 'aprob'" :disabled="!!mrs.busy" @click="pedirAprobar">
            <Icon name="check" :size="15" /> {{ m.aprobaciones.yo ? 'Quitar aprobación' : 'Aprobar' }}
          </button>
          <button class="btn go" :disabled="!!mrs.busy || !!motivoNoMerge" :title="motivoNoMerge || 'Pide tu PIN'" @click="pedirPin('mergear')">
            <Icon name="merge" :size="15" /> Mergear
          </button>
          <button v-if="esAutor" class="btn danger-ghost" :disabled="!!mrs.busy" aria-label="Cerrar el MR" @click="pedirPin('cerrar')"><Icon name="close" :size="15" /><span class="lbl-x">Cerrar</span></button>
          <p v-if="motivoNoMerge" class="why">{{ motivoNoMerge }}</p>
        </div>
      </Transition>
    </footer>
    <MrDestinoSheet />
  </article>
</template>

<style scoped>
.det { height: 100%; min-height: 0; min-width: 0; display: grid; grid-template-rows: auto minmax(0, 1fr) auto; grid-template-columns: minmax(0, 1fr); }
.scroll { min-height: 0; min-width: 0; overflow-x: hidden; overflow-y: auto; overscroll-behavior: contain; touch-action: pan-y; padding: 4px 16px 20px; display: flex; flex-direction: column; gap: 12px; }
.hd { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; }
.bar { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 8px 12px 6px 8px; touch-action: pan-y; }
.back { flex: none; height: 36px; width: 36px; display: grid; place-items: center; border-radius: var(--r-md); color: var(--text-2); transition: background 0.2s, scale 0.3s var(--spring); }
.back:hover { background: var(--surface-hover); color: var(--text); }
.back:active { scale: var(--press-scale); }
.bar :deep(.cbtn.ext) {
  flex: none;
  width: 36px;
  height: 36px;
  min-height: 36px;
  padding: 0;
  border-radius: var(--r-md);
  border-color: transparent;
  color: var(--text-2);
}
.bar :deep(.cbtn.ext:hover) { background: var(--surface-hover); border-color: transparent; color: var(--text); }
.bar :deep(.cbtn.ext:active) { scale: var(--press-scale); }
.bar :deep(.cbtn.ext.done) { color: var(--st-done); }
.repo { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 560; color: var(--text-3); }
.repo b { color: var(--text-2); }
h2 { margin: 0; font-family: var(--font-display); font-size: 20px; font-weight: 600; line-height: 1.3; letter-spacing: -0.02em; overflow-wrap: anywhere; }
.ramas { display: flex; align-items: center; flex-wrap: wrap; gap: 5px; margin: 0; font-size: 12px; color: var(--text-3); overflow-wrap: anywhere; }
.ramas i { font-style: normal; color: var(--text-4); }
.badges { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.b { display: inline-flex; align-items: center; gap: 4px; height: 22px; padding: 0 9px; border-radius: var(--r-pill); font-style: normal; font-size: var(--t-sm); font-weight: 560; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
.b.mini { height: 18px; padding: 0 7px; font-size: var(--t-xs); }
.b.who { color: var(--text-3); background: transparent; }
.b.bad { color: var(--danger); background: var(--danger-soft); box-shadow: none; }
.btn-b { transition: background 0.2s, scale 0.3s var(--spring); }
.btn-b:hover:not(:disabled) { background: var(--surface-hover); }
.btn-b:active:not(:disabled) { scale: var(--press-scale); }
.btn-b.on { color: var(--st-blocked); background: var(--st-blocked-soft); box-shadow: none; }
.blk { display: grid; gap: 10px; padding: 14px; border-radius: var(--r-lg); background: var(--surface); border: 1px solid var(--line); min-width: 0; grid-template-columns: minmax(0, 1fr); }
.blk > *, .hilo > *, .nota > *, .etapa > * { min-width: 0; }
.bh { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
h3 { margin: 0 auto 0 0; font-size: 11px; font-weight: 650; letter-spacing: 0.09em; text-transform: uppercase; color: var(--text-4); }
.count { font-size: 12px; font-weight: 600; color: var(--text-2); }
.count.good { color: var(--st-done); }
.count.bad { color: var(--danger); }
.muted { margin: 0; font-size: 13px; color: var(--text-3); }
.link { font-size: var(--t-md); font-weight: 600; color: var(--accent); }
.link:hover { text-decoration: underline; }
.a-sesion { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.ok-msg { margin: 0; font-size: var(--t-md); color: var(--st-done); }
.chip { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: var(--r-pill); border: 1px solid var(--line-2); font-size: var(--t-md); font-weight: 580; color: var(--text); background: var(--surface-2); transition: background 0.2s, scale 0.3s var(--spring), opacity 0.2s; }
.chip:hover:not(:disabled) { background: var(--surface-hover); }
.chip:active:not(:disabled) { scale: var(--press-scale); }
.chip:disabled { opacity: 0.5; cursor: default; }
.chip.go { color: var(--accent-ink); background: var(--accent); border-color: transparent; }
.etapa { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; }
.et { font-size: var(--t-sm); font-weight: 600; color: var(--text-3); text-transform: capitalize; }
.jobs { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px; min-width: 0; }
.job { display: flex; min-width: 0; align-items: center; gap: 8px; min-height: 34px; padding: 0 4px 0 8px; border-radius: var(--r-md); transition: background 0.2s; }
.job:hover { background: var(--surface-hover); }
.job.fallo { background: color-mix(in srgb, var(--danger-soft) 60%, transparent); }
.jn { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; color: var(--text); }
a.jn:hover { text-decoration: underline; }
.jd { font-size: var(--t-sm); color: var(--text-4); }
.ib { flex: none; height: 30px; width: 30px; display: grid; place-items: center; border-radius: var(--r-md); color: var(--accent); transition: background 0.2s, scale 0.3s var(--spring), rotate 0.5s var(--spring); }
.ib:hover:not(:disabled) { background: var(--accent-soft); rotate: 90deg; }
.ib:active:not(:disabled) { scale: var(--press-scale); }
.people, .pick { display: flex; flex-wrap: wrap; gap: 6px; }
.person { display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 11px; border-radius: var(--r-pill); font-size: var(--t-md); font-weight: 540; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
.person.aprob { color: var(--st-done); background: var(--st-done-soft); box-shadow: none; }
.pickable { height: 34px; transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), box-shadow 0.25s; }
.pickable:active { scale: var(--press-scale); }
.pickable.on { color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.pick-act { flex-basis: 100%; display: flex; justify-content: flex-end; gap: 6px; margin-top: 4px; }
.sub-h { display: flex; align-items: center; justify-content: space-between; font-size: 12px; font-weight: 600; color: var(--text-3); }
.desc { font-size: 14px; line-height: 1.55; overflow-wrap: anywhere; }
.hilo { display: grid; grid-template-columns: minmax(0, 1fr); gap: 8px; padding: 10px 12px; border-radius: 12px; background: var(--bg-2); border: 1px solid var(--line); }
.hilo.open { border-color: color-mix(in srgb, var(--st-blocked) 45%, transparent); }
.hilo.res { opacity: 0.62; }
.donde { display: flex; align-items: center; gap: 5px; margin: 0; font-size: var(--t-sm); color: var(--text-3); overflow-wrap: anywhere; }
.nota { display: grid; grid-template-columns: minmax(0, 1fr); gap: 4px; }
.nota + .nota { padding-top: 8px; border-top: 1px solid var(--line); }
.quien { min-width: 0; overflow-wrap: anywhere; font-size: 12px; color: var(--text-2); }
.quien i { font-style: normal; color: var(--text-4); margin-left: 4px; }
.nota.mia .quien b { color: var(--accent); }
.cuerpo { font-size: var(--t-lg); line-height: 1.55; color: var(--text); }
/* el código, las tablas y los diffs scrollean dentro de su caja: su ancho intrínseco no empuja la página */
.desc :deep(.md-code), .desc :deep(.md-table), .cuerpo :deep(.md-code), .cuerpo :deep(.md-table) { contain: inline-size; overscroll-behavior-x: contain; touch-action: pan-x pan-y; }
.desc :deep(.md-details), .cuerpo :deep(.md-details) { min-width: 0; }
.actividad { display: grid; gap: 2px; padding: 2px 2px 0; }
.act-more { justify-self: start; display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 8px; border-radius: 8px; font-size: var(--t-sm); font-weight: 600; color: var(--text-3); transition: background 0.2s, color 0.2s; }
.act-more:hover { background: var(--surface-hover); color: var(--text-2); }
.act-list { list-style: none; margin: 0; padding: 0; display: grid; }
.act { position: relative; display: flex; align-items: baseline; gap: 8px; min-width: 0; padding: 3px 4px 3px 18px; font-size: 12px; line-height: 1.4; color: var(--text-3); }
.act::before { content: ''; position: absolute; left: 7px; top: 0; bottom: 0; width: 1px; background: var(--line); }
.act:first-child::before { top: 50%; }
.act:last-child::before { bottom: 50%; }
.act:only-child::before { display: none; }
.dot { position: absolute; left: 5px; top: calc(3px + 0.7em - 2.5px); width: 5px; height: 5px; border-radius: 50%; background: var(--text-4); }
.act-t { flex: 1; min-width: 0; overflow-wrap: anywhere; }
.act-t b { font-weight: 600; color: var(--text-2); }
.veces { font-style: normal; font-weight: 600; color: var(--text-4); }
.act-f { flex: none; font-size: 11px; color: var(--text-4); }
.job.con-mandar { flex-wrap: wrap; gap: 12px; }
.ib.mandar:hover:not(:disabled) { rotate: 0deg; }
.ib.mandar.hecho { color: var(--st-done); background: var(--st-done-soft); }
.mandar-err { flex-basis: 100%; margin: 0 0 4px; font-size: var(--t-sm); color: var(--danger); overflow-wrap: anywhere; }
.hilo-acc { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.hilo-acc .mandar-err { flex-basis: auto; margin: 0; }
.resuelto { display: inline-flex; align-items: center; gap: 4px; font-size: var(--t-sm); font-weight: 600; color: var(--st-done); }
.comentar { display: grid; gap: 8px; justify-items: end; }
.comentar textarea { width: 100%; min-height: 64px; padding: 10px 12px; resize: vertical; border-radius: 12px; font: inherit; font-size: 14px; line-height: 1.45; color: var(--text); background: var(--bg-2); border: 1px solid var(--line-2); outline: none; transition: border-color 0.2s, box-shadow 0.25s; }
.comentar textarea:focus { border-color: var(--accent); box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 22%, transparent); }
.files { list-style: none; margin: 0; padding: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 2px; }
.file { min-width: 0; }
.fh { width: 100%; display: flex; align-items: center; gap: 8px; min-height: 34px; padding: 0 8px; border-radius: var(--r-md); text-align: left; transition: background 0.2s; }
.fh:hover:not(:disabled) { background: var(--surface-hover); }
.fh:disabled { cursor: default; }
.kind { flex: none; width: 18px; height: 18px; display: grid; place-items: center; border-radius: 5px; font-style: normal; font-size: var(--t-xs); font-weight: 700; color: var(--st-blocked); background: var(--st-blocked-soft); }
.kind.add { color: var(--st-done); background: var(--st-done-soft); }
.kind.del { color: var(--danger); background: var(--danger-soft); }
.kind.mv { color: var(--st-working); background: var(--st-working-soft); }
.fp { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; direction: rtl; text-align: left; font-size: 12px; color: var(--text-2); }
.chev { flex: none; color: var(--text-4); transition: rotate 0.35s var(--spring); }
.chev.rot { rotate: 90deg; }
.diff { contain: inline-size; overscroll-behavior-x: contain; touch-action: pan-x pan-y; margin: 4px 0 8px; border-radius: var(--r-md); overflow: hidden; border: 1px solid var(--line); background: var(--bg-2); animation: drop 0.35s var(--ease-out); }
.diff pre { margin: 0; max-height: 420px; overflow: auto; font-size: var(--t-sm); line-height: 1.5; }
.diff code { display: block; min-width: max-content; }
.ln { display: block; padding: 0 10px; white-space: pre; }
.ln.add { background: color-mix(in srgb, var(--st-done-soft) 80%, transparent); color: var(--st-done); }
.ln.del { background: color-mix(in srgb, var(--danger-soft) 80%, transparent); color: var(--danger); }
.ln.hunk { color: var(--text-4); background: var(--surface-2); }
.diff .muted { padding: 6px 10px; font-size: 12px; }
.acts { padding: 10px 16px calc(10px + env(safe-area-inset-bottom)); border-top: 1px solid var(--line); background: color-mix(in srgb, var(--surface) 88%, transparent); backdrop-filter: blur(10px); }
.row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.main-row .btn { flex: 1; }
.main-row .danger-ghost { flex: none; }
.why { flex-basis: 100%; margin: 0; text-align: center; font-size: 12px; color: var(--text-3); }
.confirm { display: grid; gap: 8px; }
.confirm p { margin: 0; font-size: var(--t-lg); font-weight: 560; color: var(--text); }
.confirm .btn { flex: 1; }
.btn { display: inline-flex; align-items: center; justify-content: center; gap: 7px; height: 44px; padding: 0 14px; border-radius: 12px; font-size: 14px; font-weight: 620; white-space: nowrap; transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), box-shadow 0.25s, opacity 0.2s, filter 0.2s; }
.btn:active:not(:disabled) { scale: var(--press-scale); }
.btn:disabled { opacity: 0.45; cursor: not-allowed; }
.go { background: var(--accent); color: var(--accent-ink); }
.go:hover:not(:disabled) { box-shadow: 0 0 0 4px var(--accent-soft), 0 8px 26px -10px var(--accent); }
.go.busy:disabled { opacity: 0.85; }
.ok { color: var(--st-done); background: var(--st-done-soft); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--st-done) 40%, transparent); }
.aprob:hover:not(:disabled) { filter: brightness(1.1); }
.ghost { color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line-2); }
.ghost:hover:not(:disabled) { color: var(--text); background: var(--surface-hover); }
.danger-ghost { color: var(--danger); background: transparent; box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 35%, transparent); }
.danger-ghost:hover:not(:disabled) { background: var(--danger-soft); }
.lbl-x { display: none; }
.spin { width: 14px; height: 14px; border-radius: 50%; border: 1.5px solid currentColor; border-right-color: transparent; animation: spin 0.8s linear infinite; }
@keyframes drop { from { opacity: 0; transform: translateY(-6px); } }
@media (max-width: 1023.98px) {
  .det { background: var(--bg); }
}
@media (min-width: 1024px) {
  .back { display: none; }
  .bar { padding: var(--view-pad-top) var(--gutter) 0; }
  .scroll { padding: 8px var(--gutter-end) 28px var(--gutter); gap: 14px; scrollbar-gutter: stable; }
  h2 { font-size: 24px; }
  .acts { padding: 12px var(--gutter) 14px; }
  .main-row .btn { flex: none; min-width: 150px; }
  .main-row { justify-content: flex-end; }
  .why { flex-basis: auto; order: -1; margin-right: auto; text-align: left; }
  .lbl-x { display: inline; }
  .confirm { grid-template-columns: minmax(0, 1fr) auto; align-items: center; }
  .confirm .btn { flex: none; min-width: 130px; }
}
:root[data-motion='soft'] .diff { animation: none; }
@media (prefers-reduced-motion: reduce) { .diff { animation: none; } }
</style>
