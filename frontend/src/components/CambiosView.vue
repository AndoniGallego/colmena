<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { mover, teclaMovimiento } from '../lib/cambios'
import { parseDiff } from '../lib/diff'
import {
  etiquetaRango, largoEstimado, limites, MAX_COMENTARIOS, MAX_MENSAJE, rangoDe, seleccionable, tocar,
  type RangoDiff, type Seleccion,
} from '../lib/diffComentarios'
import { cambios, cargarCambios } from '../state/cambios'
import { agregar, editar, faseDe, mandar, pendientes, quitar } from '../state/diffComentarios'
import { irAMr, mrDeSesion } from '../state/mrs'
import DiffComentarioForm from './DiffComentarioForm.vue'
import DiffComentarioSheet from './DiffComentarioSheet.vue'
import DiffComentariosLista from './DiffComentariosLista.vue'
import Icon from './Icon.vue'
import InlineAlert from './InlineAlert.vue'

const props = defineProps<{ sid: string; desktop: boolean }>()

const root = ref<HTMLElement | null>(null)
const verCommits = ref(false)
const sel = ref('')
const enDiff = ref(false)

const data = computed(() => cambios.data)
const archivos = computed(() => data.value?.archivos ?? [])
const idx = computed(() => archivos.value.findIndex((a) => a.path === sel.value))
const actual = computed(() => (idx.value >= 0 ? archivos.value[idx.value] : null))
const lineas = computed(() => parseDiff(actual.value?.diff ?? ''))
const mr = computed(() => mrDeSesion(props.sid))
const plural = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`

const selec = ref<Seleccion | null>(null)
const form = ref<{ rango: RangoDiff; ultimo: number; editId: string } | null>(null)
const texto = ref('')
const listaAbierta = ref(false)
const avisoLocal = ref('')

const pend = computed(() => pendientes(props.sid))
const fase = computed(() => faseDe(props.sid))
const rangoSel = computed(() => {
  if (!selec.value) return null
  const [a, b] = limites(selec.value)
  return rangoDe(lineas.value, a, b)
})
const demasiado = computed(() => largoEstimado(pend.value) > MAX_MENSAJE)
const ultimoForm = computed(() => (form.value ? Math.min(form.value.ultimo, lineas.value.length - 1) : -1))
const etiquetaForm = computed(() => (form.value ? `${actual.value?.path ?? ''}:${etiquetaRango(form.value.rango)}` : ''))

/** Por índice de línea: los comentarios pendientes de este archivo que la cubren (el último trae el chip). */
const marcas = computed(() => {
  const out = new Map<number, { n: number; id: string; ultimo: boolean }[]>()
  const path = actual.value?.path
  pend.value.forEach((c, k) => {
    if (c.path !== path) return
    const idxs: number[] = []
    lineas.value.forEach((l, i) => {
      const n = c.lado === 'nuevo' ? l.b : l.k === 'del' ? l.a : null
      if (n !== null && n >= c.desde && n <= c.hasta) idxs.push(i)
    })
    idxs.forEach((i, j) => out.set(i, [...(out.get(i) ?? []), { n: k + 1, id: c.id, ultimo: j === idxs.length - 1 }]))
  })
  return out
})

const enSel = (i: number) => !!selec.value && i >= limites(selec.value)[0] && i <= limites(selec.value)[1]

function marcarLinea(i: number) {
  if (form.value || !seleccionable(lineas.value[i])) return
  const sig = tocar(selec.value, i)
  const [a, b] = limites(sig)
  if (!rangoDe(lineas.value, a, b)) return
  selec.value = sig
}

function clicLinea(i: number) {
  if (!props.desktop) return
  const sel = typeof window !== 'undefined' ? window.getSelection() : null
  if (sel && !sel.isCollapsed) return
  marcarLinea(i)
}

function abrirForm() {
  const r = rangoSel.value
  if (!r || !selec.value) return
  avisoLocal.value = ''
  texto.value = ''
  form.value = { rango: r, ultimo: limites(selec.value)[1], editId: '' }
}

function editarDesdeChip(id: string, ultimo: number) {
  const c = pend.value.find((x) => x.id === id)
  if (!c) return
  selec.value = null
  texto.value = c.texto
  form.value = { rango: { lado: c.lado, desde: c.desde, hasta: c.hasta, fragmento: c.fragmento }, ultimo, editId: id }
}

function cerrarForm() {
  form.value = null
  texto.value = ''
}

function guardarForm() {
  const f = form.value
  const t = texto.value.trim()
  if (!f || !t || !actual.value) return
  if (f.editId) editar(props.sid, f.editId, t)
  else if (!agregar(props.sid, { path: actual.value.path, ...f.rango, texto: t })) {
    avisoLocal.value = `Ya hay ${MAX_COMENTARIOS} comentarios: mandalos antes de seguir`
    return
  }
  selec.value = null
  cerrarForm()
}

const enviar = () => mandar(props.sid)

// Si Actualizar cambia el diff, lo marcado ya no apunta a lo mismo; el comentario que se está escribiendo se conserva.
watch(
  () => actual.value?.diff,
  () => {
    selec.value = null
  },
)

watch(sel, () => {
  selec.value = null
  cerrarForm()
})

watch(
  archivos,
  (lista) => {
    if (lista.some((a) => a.path === sel.value)) return
    sel.value = props.desktop && lista.length ? lista[0].path : ''
    enDiff.value = false
  },
  { immediate: true },
)

function elegir(path: string) {
  sel.value = path
  if (!props.desktop) enDiff.value = true
}

function onKey(e: KeyboardEvent) {
  const d = teclaMovimiento(e.key)
  if (!d || e.ctrlKey || e.metaKey || e.altKey) return
  const t = e.target as HTMLElement | null
  if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA')) return
  const i = mover(idx.value, d, archivos.value.length)
  if (i < 0) return
  e.preventDefault()
  sel.value = archivos.value[i].path
  nextTick(() => root.value?.querySelector<HTMLElement>('[aria-current="true"]')?.scrollIntoView?.({ block: 'nearest' }))
}

const refrescar = () => cargarCambios(props.sid, true)

onMounted(() => {
  cargarCambios(props.sid)
  if (props.desktop) root.value?.focus({ preventScroll: true })
})
</script>

<template>
  <section ref="root" class="cambios" tabindex="0" aria-label="Cambios de la sesión" @keydown="onKey">
    <p v-if="cambios.error" class="aviso err" role="alert">{{ cambios.error }}</p>

    <template v-if="data">
      <header v-if="data.repo && !(enDiff && !desktop)" class="top">
        <div class="linea">
          <Icon name="branch" :size="14" />
          <span class="rama mono" :title="data.rama">{{ data.rama || 'HEAD suelto' }}</span>
          <template v-if="data.base">
            <span class="sobre">sobre</span>
            <span class="base mono">{{ data.base }}</span>
          </template>
          <span class="grow" />
          <a v-if="mr" href="#" data-test="ver-mr" class="chip" @click.prevent="irAMr(mr.ref)">Ver MR</a>
          <button type="button" class="chip" data-test="actualizar" :disabled="cambios.loading" :aria-busy="cambios.loading" @click="refrescar">
            <Icon name="refresh" :size="13" /><span>Actualizar</span>
          </button>
        </div>
        <div v-if="pend.length" class="linea acc">
          <button type="button" class="chip prim hit" data-test="mandar" :disabled="demasiado || fase.fase === 'enviando'" :aria-busy="fase.fase === 'enviando'" @click="enviar">
            Mandar a la sesión ({{ pend.length }})
          </button>
          <button type="button" class="chip hit" data-test="ver-comentarios" @click="listaAbierta = true">Ver comentarios</button>
        </div>
        <div class="linea sub">
          <button v-if="data.commits_total" type="button" class="link" data-test="commits" :aria-expanded="verCommits" @click="verCommits = !verCommits">
            {{ plural(data.commits_total, 'commit', 'commits') }}
            <Icon name="chevron" :size="12" class="chev" :class="{ rot: verCommits }" />
          </button>
          <span v-else class="mudo">sin commits propios</span>
          <span v-if="data.sin_guardar" class="mudo">sin guardar: {{ plural(data.sin_guardar, 'archivo', 'archivos') }}</span>
        </div>
        <ul v-if="verCommits" class="commits">
          <li v-for="c in data.commits" :key="c.sha"><span class="sha mono">{{ c.sha }}</span> {{ c.titulo }}</li>
          <li v-if="data.commits_total > data.commits.length" class="mudo">y {{ data.commits_total - data.commits.length }} más</li>
        </ul>
      </header>

      <div v-if="fase.fase === 'ok' || fase.fase === 'error' || demasiado || avisoLocal" class="avisos">
        <p v-if="fase.fase === 'ok'" class="ok" role="status">Comentarios mandados</p>
        <InlineAlert v-if="fase.fase === 'error'">{{ fase.error }}</InlineAlert>
        <InlineAlert v-if="demasiado" tone="warn">Es mucho para un solo mensaje: mandá menos comentarios por vez</InlineAlert>
        <InlineAlert v-if="avisoLocal" tone="warn">{{ avisoLocal }}</InlineAlert>
      </div>

      <p v-if="!data.repo" class="vacio">No es un repo git</p>
      <p v-else-if="!archivos.length" class="vacio">Sin cambios respecto de {{ data.base || 'la base' }}</p>

      <div v-else class="cuerpo" :class="{ ancho: desktop }">
        <ul v-if="desktop || !enDiff" class="lista" aria-label="Archivos cambiados">
          <li v-for="a in archivos" :key="a.path">
            <button
              type="button"
              class="arch"
              data-test="archivo"
              :class="{ on: a.path === sel }"
              :aria-current="a.path === sel ? 'true' : undefined"
              @click="elegir(a.path)"
            >
              <i class="kind" :class="a.estado">{{ a.estado }}</i>
              <span class="ruta mono" :title="a.path">{{ a.path }}</span>
              <span v-if="a.adds" class="n add mono">+{{ a.adds }}</span>
              <span v-if="a.dels" class="n del mono">−{{ a.dels }}</span>
            </button>
          </li>
        </ul>

        <div v-if="actual && (desktop || enDiff)" class="visor" data-test="diff">
          <div class="vh">
            <button v-if="!desktop" type="button" class="chip" data-test="volver-lista" @click="enDiff = false">
              <Icon name="back" :size="13" /><span>Archivos</span>
            </button>
            <span class="ruta mono" :title="actual.path">{{ actual.path }}</span>
            <button v-if="!desktop && pend.length" type="button" class="chip prim hit" data-test="mandar" :disabled="demasiado || fase.fase === 'enviando'" :aria-busy="fase.fase === 'enviando'" @click="enviar">
              Mandar a la sesión ({{ pend.length }})
            </button>
            <button v-if="!desktop && pend.length" type="button" class="chip hit" data-test="ver-comentarios" @click="listaAbierta = true">Ver</button>
          </div>
          <div class="codigo">
            <p v-if="actual.binario" class="nota">Binario: no se muestra el diff.</p>
            <p v-else-if="!lineas.length" class="nota">Sin diff para mostrar.</p>
            <div v-else class="lineas mono">
              <template v-for="(l, i) in lineas" :key="i">
                <div
                  data-test="linea"
                  class="ln"
                  :class="[l.k, { sel: enSel(i), comentada: marcas.has(i), elegible: l.k !== 'hunk' }]"
                  :aria-selected="enSel(i) ? 'true' : undefined"
                  @click="clicLinea(i)"
                >
                  <button
                    v-if="l.k !== 'hunk'"
                    type="button"
                    class="gut"
                    data-test="marcar"
                    :aria-label="`Línea ${l.b ?? l.a}, marcar`"
                    @click.stop="marcarLinea(i)"
                  >
                    <span class="num" data-test="num-a">{{ l.a ?? '' }}</span>
                    <span class="num" data-test="num-b">{{ l.b ?? '' }}</span>
                  </button>
                  <template v-else>
                    <span class="num" data-test="num-a">{{ l.a ?? '' }}</span>
                    <span class="num" data-test="num-b">{{ l.b ?? '' }}</span>
                  </template>
                  <span class="sig">{{ l.k === 'add' ? '+' : l.k === 'del' ? '−' : '' }}</span>
                  <span class="txt">{{ l.t || ' ' }}</span>
                  <template v-for="m in marcas.get(i) ?? []" :key="m.id">
                    <button
                      v-if="m.ultimo"
                      type="button"
                      class="chipc"
                      data-test="chip-comentario"
                      :aria-label="`Comentario ${m.n}, editar`"
                      @click.stop="editarDesdeChip(m.id, i)"
                    >{{ m.n }}</button>
                  </template>
                </div>
                <DiffComentarioForm
                  v-if="form && desktop && ultimoForm === i"
                  v-model="texto"
                  class="dcf-inline"
                  :etiqueta="etiquetaForm"
                  :fragmento="form.rango.fragmento"
                  :editando="!!form.editId"
                  autoenfocar
                  @agregar="guardarForm"
                  @cancelar="cerrarForm"
                />
              </template>
            </div>
            <p v-if="actual.truncado" class="nota">Diff recortado por tamaño: el resto está en el repo.</p>
          </div>
          <div v-if="rangoSel && !form" class="barra" data-test="barra-comentar">
            <button type="button" class="btn btn-primary hit" data-test="comentar" @click="abrirForm">Comentar {{ etiquetaRango(rangoSel) }}</button>
            <button type="button" class="btn btn-ghost hit" data-test="limpiar-seleccion" @click="selec = null">Limpiar</button>
          </div>
        </div>
      </div>
      <p v-if="data.truncado && archivos.length" class="pie">Hay archivos con el diff recortado por tamaño.</p>
    </template>

    <p v-else-if="cambios.loading" class="vacio" role="status">Leyendo los cambios…</p>

    <DiffComentarioSheet :open="!!form && !desktop" :titulo="`Comentar ${form ? etiquetaRango(form.rango) : ''}`" test-id="comentario-sheet" @close="cerrarForm">
      <DiffComentarioForm
        v-if="form && !desktop"
        v-model="texto"
        :etiqueta="etiquetaForm"
        :fragmento="form.rango.fragmento"
        :editando="!!form.editId"
        autoenfocar
        @agregar="guardarForm"
        @cancelar="cerrarForm"
      />
    </DiffComentarioSheet>
    <DiffComentariosLista :open="listaAbierta" :comentarios="pend" @close="listaAbierta = false" @editar="(id, t) => editar(sid, id, t)" @quitar="(id) => quitar(sid, id)" />
  </section>
</template>

<style scoped>
.cambios { flex: 1; min-height: 0; display: flex; flex-direction: column; background: var(--bg); outline: none; overflow: hidden; }
.top { flex: none; padding: 10px var(--gutter) 8px; border-bottom: 1px solid var(--line); display: flex; flex-direction: column; gap: 6px; }
.linea { display: flex; align-items: center; gap: 8px; min-width: 0; font-size: 13px; color: var(--text-2); }
.linea.sub { font-size: var(--t-md); gap: 14px; }
.grow { flex: 1; }
.rama { color: var(--text); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.sobre, .mudo { color: var(--text-4); }
.base { color: var(--text-3, var(--text-2)); }
.chip { flex: none; display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 10px; border-radius: 8px; font-size: 12px; font-weight: 600; color: var(--text-2); box-shadow: inset 0 0 0 1px var(--line-2); text-decoration: none; }
.chip:hover:not(:disabled) { color: var(--text); background: var(--accent-soft); }
.chip:disabled { opacity: 0.55; cursor: not-allowed; }
.link { display: inline-flex; align-items: center; gap: 4px; color: var(--text-2); font-weight: 600; }
.link:hover { color: var(--text); }
.chev { transition: rotate 0.2s; }
.chev.rot { rotate: 90deg; }
.commits { list-style: none; margin: 0; padding: 0; max-height: 30vh; overflow: auto; font-size: var(--t-md); color: var(--text-2); display: flex; flex-direction: column; gap: 3px; }
.sha { color: var(--text-4); margin-right: 6px; }
.aviso.err { margin: 10px var(--gutter); color: var(--danger); font-size: 13px; }
.vacio { margin: 0; padding: 36px var(--gutter); text-align: center; color: var(--text-3, var(--text-2)); font-size: 14px; }
.pie { flex: none; margin: 0; padding: 6px var(--gutter); font-size: 12px; color: var(--text-4); border-top: 1px solid var(--line); }
.cuerpo { flex: 1; min-height: 0; display: flex; flex-direction: column; }
.cuerpo.ancho { display: grid; grid-template-columns: minmax(220px, 340px) minmax(0, 1fr); }
.lista { list-style: none; margin: 0; padding: 6px 0; overflow-y: auto; overscroll-behavior: contain; min-height: 0; flex: 1; }
.cuerpo.ancho .lista { flex: none; border-right: 1px solid var(--line); }
.arch { width: 100%; display: flex; align-items: center; gap: 8px; padding: 8px var(--gutter); min-height: 40px; text-align: left; font-size: 13px; color: var(--text-2); }
.arch:hover { background: var(--surface-2); }
.arch.on { background: var(--accent-soft); color: var(--text); }
.ruta { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.n { flex: none; font-size: 12px; }
.n.add { color: var(--st-done); }
.n.del { color: var(--danger); }
.kind { flex: none; width: 18px; font-style: normal; font-size: 11px; font-weight: 700; text-align: center; color: var(--text-4); }
.kind.A { color: var(--st-done); }
.kind.D { color: var(--danger); }
.visor { flex: 1; min-width: 0; min-height: 0; display: flex; flex-direction: column; }
.vh { flex: none; display: flex; align-items: center; gap: 10px; padding: 8px var(--gutter); border-bottom: 1px solid var(--line); font-size: var(--t-md); color: var(--text-2); }
.codigo { flex: 1; min-height: 0; overflow: auto; overscroll-behavior: contain; }
.lineas { min-width: max-content; font-size: 12px; line-height: 1.55; padding: 4px 0; }
.ln { --tint: transparent; display: flex; white-space: pre; background: var(--tint); }
.gut { flex: none; position: sticky; left: 0; z-index: 1; display: flex; padding: 0; background: linear-gradient(var(--tint), var(--tint)), var(--bg); color: inherit; font: inherit; cursor: pointer; touch-action: manipulation; }
.num { flex: none; width: 4ch; padding: 0 6px; text-align: right; color: var(--text-4); user-select: none; }
.sig { flex: none; width: 2ch; color: var(--text-4); user-select: none; }
.txt { padding-right: 14px; }
.ln.add { --tint: color-mix(in srgb, var(--st-done-soft) 80%, transparent); }
.ln.add .sig, .ln.add .txt { color: var(--st-done); }
.ln.del { --tint: color-mix(in srgb, var(--danger-soft) 80%, transparent); }
.ln.del .sig, .ln.del .txt { color: var(--danger); }
.ln.hunk { --tint: var(--surface-2); color: var(--text-4); }
.ln.hunk .txt { padding-left: 2ch; }
.ln.sel { --tint: var(--accent-soft); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 45%, transparent); }
.ln.comentada { box-shadow: inset 3px 0 0 var(--accent); }
.ln.comentada .gut { box-shadow: inset 3px 0 0 var(--accent); }
.ln.sel .gut { box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 45%, transparent); }
.ln.sel.comentada .gut { box-shadow: inset 3px 0 0 var(--accent), inset 0 0 0 1px color-mix(in srgb, var(--accent) 45%, transparent); }
.ln.sel.comentada { box-shadow: inset 3px 0 0 var(--accent), inset 0 0 0 1px color-mix(in srgb, var(--accent) 45%, transparent); }
.chipc { flex: none; align-self: center; min-width: 20px; height: 18px; margin: 0 6px 0 auto; padding: 0 6px; border-radius: var(--r-pill); font-size: 11px; font-weight: 700; line-height: 18px; color: var(--accent-ink, #fff); background: var(--accent); position: sticky; right: 8px; }
.dcf-inline { position: sticky; left: 0; width: min(560px, calc(100vw - 2 * var(--gutter))); margin: 6px var(--gutter) 8px; box-sizing: border-box; }
.barra { flex: none; display: flex; gap: 8px; padding: 8px var(--gutter) max(8px, env(safe-area-inset-bottom)); border-top: 1px solid var(--line); background: var(--bg); }
.barra .btn { touch-action: manipulation; }
.chip.prim { color: var(--accent); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--accent) 55%, transparent); }
.linea.acc { flex-wrap: wrap; }
.avisos { flex: none; display: grid; gap: 6px; padding: 8px var(--gutter) 0; }
.ok { margin: 0; font-size: 13px; color: var(--st-done); }
@media (pointer: coarse) {
  .ln.elegible { min-height: 36px; align-items: center; }
  .gut { align-self: stretch; align-items: center; }
  .gut .num { width: 5ch; }
}
.nota { margin: 0; padding: 12px var(--gutter); font-size: var(--t-md); color: var(--text-4); }
</style>
