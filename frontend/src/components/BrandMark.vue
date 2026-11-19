<script setup lang="ts">
import { computed } from 'vue'
import type { LogoVariant } from '../lib/colmena'
import { logoVariant } from '../state/logo'
import { MARK_DEFAULTS, type MarkProps } from './logo/marca'
import LogoPanal from './logo/LogoPanal.vue'
import LogoAbeja from './logo/LogoAbeja.vue'
import LogoMonograma from './logo/LogoMonograma.vue'

const props = withDefaults(defineProps<MarkProps & { variant?: LogoVariant }>(), MARK_DEFAULTS)

const COMPS = { panal: LogoPanal, abeja: LogoAbeja, monograma: LogoMonograma }
const comp = computed(() => COMPS[props.variant ?? logoVariant.value])
const pass = computed(() => {
  const { variant: _v, ...rest } = props
  return rest
})
</script>

<template>
  <component :is="comp" :key="variant ?? logoVariant" v-bind="pass" class="brand-mark" :class="{ off: !live, glow: size >= 40 }" />
</template>

<style>
.brand-mark {
  --mark-ink: var(--text);
  --mark-lit: var(--accent);
  --mark-dim: color-mix(in srgb, var(--text) 15%, transparent);
  --mark-alert: var(--st-blocked);
}
:root[data-theme='dark'] .brand-mark.glow .lit,
:root[data-theme='dark'] .brand-mark.glow .bee {
  filter: drop-shadow(0 0 2.2px color-mix(in srgb, var(--mark-lit) 55%, transparent));
}
.brand-mark.off {
  --mark-lit: var(--text-3);
}
</style>
