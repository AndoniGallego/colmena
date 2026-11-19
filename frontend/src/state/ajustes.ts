import { ref, watch } from 'vue'
import { auth } from './app'

export const ajustesOpen = ref(false)
let pushed = false

export function openAjustes() {
  if (ajustesOpen.value) return
  history.pushState({ ...(history.state ?? {}), orqAjustes: true }, '')
  pushed = true
  ajustesOpen.value = true
}

export function closeAjustes() {
  if (!ajustesOpen.value) return
  if (pushed && history.state?.orqAjustes) history.back()
  else {
    pushed = false
    ajustesOpen.value = false
  }
}

window.addEventListener('popstate', () => {
  if (ajustesOpen.value && !history.state?.orqAjustes) {
    ajustesOpen.value = false
    pushed = false
  }
})

watch(auth, (a) => {
  if (a !== 'ready') {
    ajustesOpen.value = false
    pushed = false
  }
})
