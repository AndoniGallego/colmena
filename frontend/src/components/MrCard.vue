<script setup lang="ts">
import type { Mr } from '../api/mrsApi'
import { ago, fechaLarga } from '../lib/time'
import { mrs, pausar } from '../state/mrs'
import Icon from './Icon.vue'
import MrPipe from './MrPipe.vue'

defineProps<{ m: Mr; now: number; pausado?: boolean }>()
const emit = defineEmits<{ open: [ref: string] }>()

function tituloCreado(iso: string) {
  const f = fechaLarga(iso)
  return f ? `Creado el ${f}` : ''
}
</script>

<template>
  <div class="card" :class="{ atenuado: pausado }">
    <button
      class="item"
      :class="{ sel: m.ref === mrs.sel, draft: m.draft }"
      :aria-current="m.ref === mrs.sel"
      :title="tituloCreado(m.creado)"
      @click="emit('open', m.ref)"
    >
      <span class="top">
        <span class="repo">{{ m.repo_corto }} <b class="mono">!{{ m.iid }}</b></span>
        <span class="meta">
          <span v-if="m.actualizado" class="age">{{ ago(m.actualizado, now) }}</span>
          <MrPipe :estado="m.pipeline.estado" />
        </span>
      </span>
      <span class="tit">{{ m.titulo }}</span>
      <span class="ramas mono"><Icon name="branch" :size="12" /> <span class="r">{{ m.rama }}</span> <i>→</i> <span class="r t">{{ m.target }}</span></span>
      <span class="badges">
        <i v-if="pausado" class="b pausa"><Icon name="pause" :size="10" /> En pausa</i>
        <i v-if="m.rol === 'revisor'" class="b who">de {{ m.autor.nombre || m.autor.username }}</i>
        <i v-if="m.draft" class="b">Draft</i>
        <i v-if="m.conflictos" class="b bad"><Icon name="warn" :size="11" /> Conflictos</i>
        <i class="b" :class="{ good: m.aprobaciones.faltan === 0 && m.aprobaciones.dadas > 0, me: m.aprobaciones.yo }">
          <Icon name="check" :size="11" /> {{ m.aprobaciones.dadas }}<template v-if="m.aprobaciones.requeridas">/{{ m.aprobaciones.requeridas }}</template>
        </i>
        <i v-if="m.hilos_sin_resolver" class="b"><Icon name="chat" :size="11" /> {{ m.hilos_sin_resolver }} sin resolver</i>
        <i v-if="m.comentarios_nuevos" class="b new">{{ m.comentarios_nuevos === 1 ? '1 nuevo' : `${m.comentarios_nuevos} nuevos` }}</i>
      </span>
    </button>
    <button v-if="pausado" type="button" class="sacar hit" :disabled="!!mrs.busy" @click="void pausar(m.ref, false)">
      <Icon name="play" :size="10" /> Sacar de pausa
    </button>
  </div>
</template>

<style scoped>
.card { position: relative; display: grid; }
.card.atenuado .item { padding-bottom: 46px; opacity: 0.72; transition: opacity 0.25s, background 0.2s, border-color 0.25s, scale 0.3s var(--spring); }
.card.atenuado:hover .item, .card.atenuado .item.sel { opacity: 1; }
.item { position: relative; width: 100%; min-width: 0; display: grid; grid-template-columns: minmax(0, 1fr); gap: 6px; padding: 12px 14px; text-align: left; border-radius: var(--r-lg); background: var(--surface); border: 1px solid var(--line); transition: background 0.2s, border-color 0.25s, scale 0.3s var(--spring), box-shadow 0.3s; }
.item:hover { background: var(--surface-hover); }
.item:active { scale: 0.985; }
.item.sel { border-color: var(--accent-line); box-shadow: 0 0 0 3px var(--accent-soft); }
.item.draft .tit { color: var(--text-2); }
.top { display: flex; align-items: center; justify-content: space-between; gap: 8px; min-width: 0; }
.meta { display: flex; align-items: center; gap: 8px; flex: none; }
.age { font-size: 11px; font-weight: 560; color: var(--text-3); white-space: nowrap; }
.repo { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 560; color: var(--text-3); }
.repo b { font-weight: 600; color: var(--text-2); }
.tit { font-size: 14.5px; font-weight: 600; line-height: 1.35; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }
.ramas { display: flex; align-items: center; gap: 5px; min-width: 0; font-size: var(--t-sm); color: var(--text-3); }
.ramas :deep(svg) { flex: none; color: var(--text-4); }
.ramas i { font-style: normal; color: var(--text-4); }
.r { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.r.t { flex: none; max-width: 40%; }
.badges { display: flex; flex-wrap: wrap; gap: 5px; }
.b { display: inline-flex; align-items: center; gap: 4px; height: 21px; padding: 0 8px; border-radius: var(--r-pill); font-style: normal; font-size: var(--t-sm); font-weight: 560; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
.b.who { color: var(--text-3); background: transparent; }
.b.pausa { color: var(--text-3); background: var(--surface-2); }
.b.bad { color: var(--danger); background: var(--danger-soft); box-shadow: none; }
.b.good { color: var(--st-done); background: var(--st-done-soft); box-shadow: none; }
.b.me { box-shadow: inset 0 0 0 1px var(--st-done); }
.b.new { color: var(--accent); background: var(--accent-soft); box-shadow: none; }
.sacar { position: absolute; right: 10px; bottom: 10px; display: inline-flex; align-items: center; gap: 5px; height: 26px; padding: 0 10px; background: var(--surface); border-radius: var(--r-pill); font-size: var(--t-sm); font-weight: 600; color: var(--text-2); box-shadow: inset 0 0 0 1px var(--line-2); transition: background 0.2s, color 0.2s, scale 0.3s var(--spring); }
.sacar:active:not(:disabled) { scale: var(--press-scale); }
.sacar:hover:not(:disabled) { background: var(--surface-hover); color: var(--text); }
.sacar:disabled { opacity: 0.5; }
</style>
