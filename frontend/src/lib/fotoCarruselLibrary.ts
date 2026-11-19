/** Acción "Ver en Biblioteca": abre el ítem y cierra el carrusel para no tapar la Biblioteca. */
export function actVerEnBiblioteca(
  id: string | undefined,
  openInLibrary: (id: string) => void,
  emitClose: () => void,
) {
  if (id == null || id === '') return
  openInLibrary(id)
  emitClose()
}
