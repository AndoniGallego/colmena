import { ApiError, type Api, type Nota } from '../api/types'

const hace = (min: number) => new Date(Date.now() - min * 60_000).toISOString()

function ejemplo(): Nota[] {
  return [
    { id: 'n1', tipo: 'recordatorio', texto: 'Revisar el MR de la política de permisos antes de mañana', hecha_at: null, creada_at: hace(20), editada_at: hace(20), origen: null },
    { id: 'n2', tipo: 'recordatorio', texto: 'Probar el túnel desde la PC', hecha_at: hace(30), creada_at: hace(300), editada_at: hace(30), origen: null },
    { id: 'n3', tipo: 'apunte', texto: 'El puerto 8080 de la tienda local no sale por Tailscale, solo por el túnel de casa', hecha_at: null, creada_at: hace(600), editada_at: hace(600), origen: null },
    { id: 'n4', tipo: 'apunte', texto: 'Acordarse de preguntarle a Bruno por el flujo de pedidos', hecha_at: null, creada_at: hace(1500), editada_at: hace(1500), origen: { sid: '5f0c2a71-8e4b-4d0a-9a51-2c7e3b9d1f64', nombre: 'Entorno local Tienda', ts: hace(1500) } },
  ]
}

export function createMockNotas(): Pick<Api, 'listarNotas' | 'crearNota' | 'editarNota' | 'borrarNota'> {
  let lista = ejemplo()
  let version = 1
  let seq = 4
  const pend = () => lista.filter((n) => n.tipo === 'recordatorio' && !n.hecha_at).length
  const buscar = (id: string) => {
    const n = lista.find((x) => x.id === id)
    if (!n) throw new ApiError(404, 'Nota no encontrada')
    return n
  }
  return {
    listarNotas: async () => ({ notas: lista.map((n) => ({ ...n })), pendientes: pend(), version }),
    crearNota: async (b) => {
      const ahora = new Date().toISOString()
      const n: Nota = { id: `n${++seq}`, tipo: b.tipo, texto: b.texto, hecha_at: null, creada_at: ahora, editada_at: ahora, origen: b.origen ?? null }
      lista = [...lista, n]
      version++
      return { ...n }
    },
    editarNota: async (id, b) => {
      const n = buscar(id)
      const tipo = b.tipo ?? n.tipo
      const hecha_at = tipo === 'apunte' ? null : b.hecha === undefined ? n.hecha_at : b.hecha ? new Date().toISOString() : null
      const nueva: Nota = { ...n, tipo, texto: b.texto ?? n.texto, hecha_at, editada_at: new Date().toISOString() }
      lista = lista.map((x) => (x.id === id ? nueva : x))
      version++
      return { ...nueva }
    },
    borrarNota: async (id) => {
      buscar(id)
      lista = lista.filter((x) => x.id !== id)
      version++
    },
  }
}
