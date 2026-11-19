<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps<{ src: string; title: string; preview?: boolean }>()
const emit = defineEmits<{ load: []; stalled: [] }>()

const STALL_MS = 8000
const loaded = ref(false)
let timer: ReturnType<typeof setTimeout> | undefined

function arm() {
  loaded.value = false
  clearTimeout(timer)
  if (!props.preview) timer = setTimeout(() => !loaded.value && emit('stalled'), STALL_MS)
}
function onLoad() {
  loaded.value = true
  clearTimeout(timer)
  emit('load')
}

watch(() => props.src, arm)
onMounted(arm)
onBeforeUnmount(() => clearTimeout(timer))
</script>

<template>
  <iframe
    :class="['frame', { preview, loaded }]"
    :src="src"
    :title="title"
    sandbox="allow-scripts"
    referrerpolicy="no-referrer"
    allow=""
    credentialless=""
    :tabindex="preview ? -1 : 0"
    @load="onLoad"
  />
</template>

<style scoped>
.frame {
  width: 100%;
  height: 100%;
  border: 0;
  display: block;
  background: #fff;
  opacity: 0;
  transition: opacity 0.35s var(--ease-out);
}
.frame.loaded {
  opacity: 1;
}
.frame.preview {
  position: absolute;
  top: 0;
  left: 0;
  width: 1280px;
  height: 800px;
  transform-origin: 0 0;
  transform: scale(var(--s, 0.2));
  pointer-events: none;
}
:root[data-motion='soft'] .frame {
  transition-duration: 0.15s;
}
</style>
