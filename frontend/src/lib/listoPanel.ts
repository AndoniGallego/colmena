import { onBeforeUnmount, ref } from 'vue'

export function useListoPanel(cerrar: () => void, ms = 1100) {
  const listo = ref(false)
  const listoTxt = ref('')
  let timer: ReturnType<typeof setTimeout> | undefined

  function mostrarListo(texto: string) {
    listoTxt.value = texto
    listo.value = true
    clearTimeout(timer)
    timer = setTimeout(() => {
      listo.value = false
      cerrar()
    }, ms)
  }

  onBeforeUnmount(() => clearTimeout(timer))
  return { listo, listoTxt, mostrarListo }
}
