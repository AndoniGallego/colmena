<script setup lang="ts">
import { ref } from 'vue'
import { attachmentLabel, kindFromId, uploadSrc } from '../lib/attachments'
import Icon from './Icon.vue'

withDefaults(defineProps<{ ids: string[]; images?: number; solo?: boolean }>(), { images: 0, solo: false })
const broken = ref<Record<string, boolean>>({})
</script>

<template>
  <ul class="files" :class="{ solo }">
    <li v-for="id in ids" :key="id">
      <a
        v-if="kindFromId(id) === 'image' && !broken[id]"
        class="shot"
        :href="uploadSrc(id)"
        target="_blank"
        rel="noopener noreferrer"
        :title="attachmentLabel(id)"
      >
        <img :src="uploadSrc(id)" :alt="attachmentLabel(id)" loading="lazy" @error="broken[id] = true" />
      </a>
      <a v-else class="doc" :href="uploadSrc(id)" target="_blank" rel="noopener noreferrer">
        <Icon :name="kindFromId(id) === 'image' ? 'image' : 'doc'" :size="15" />
        <span>{{ attachmentLabel(id) }}</span>
      </a>
    </li>
    <li v-for="n in images" :key="`i${n}`" class="doc inline">
      <Icon name="image" :size="15" /> <span>Imagen adjunta</span>
    </li>
  </ul>
</template>

<style scoped>
.files {
  list-style: none;
  margin: 0 0 8px;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.files.solo {
  margin: 0;
}
.shot {
  display: block;
  width: 132px;
  height: 100px;
  border-radius: var(--r-md);
  overflow: hidden;
  box-shadow: 0 0 0 1px var(--line-2);
  background: var(--surface);
  transition: scale 0.35s var(--spring), box-shadow 0.25s;
}
.shot:hover {
  scale: 1.03;
  box-shadow: 0 0 0 1px var(--accent-line), 0 10px 24px -12px var(--accent);
}
.shot img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  outline: 1px solid var(--img-outline);
  outline-offset: -1px;
}
.doc {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  max-width: 220px;
  height: 30px;
  padding: 0 10px;
  border-radius: var(--r-md);
  font-size: var(--t-md);
  color: var(--text-2);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
.doc span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
