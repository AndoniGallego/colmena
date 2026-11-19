import { ApiError, type Api, type MemoriaEstado, type PasoMemoria } from '../api/types'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const engramCaido = () => new URLSearchParams(location.search).get('falla') === 'engram'

const SID = '5f0c2a71-8e4b-4d0a-9a51-2c7e3b9d1f64'
const SID2 = 'b81e44d2-37a9-4c1f-8e0d-6a2f9c04e713'

export const PIDE_MEMORIA = /decidimos|en qué quedó|levantamos|record[aá]s|memoria|egress/i

export function pasosMemoria(): PasoMemoria[] {
  return [
    { name: 'mcp__memoria__buscar_memoria', summary: 'tienda local docker egress' },
    { name: 'mcp__memoria__buscar_sesiones', summary: 'entorno local tienda docker' },
    { name: 'mcp__memoria__leer_sesion', summary: 'Entorno local Tienda · 2026-10-01' },
  ]
}

export function respuestaMemoria(): string {
  const sinEngram = engramCaido()
  const fuentes = [
    { tipo: 'sesion', session_id: SID, turno: 128, titulo: 'Entorno local Tienda', fecha: '2026-10-01' },
    { tipo: 'sesion', session_id: SID2, turno: 42, titulo: 'Límites de RAM en compose', fecha: '2026-10-02' },
    ...(sinEngram ? [] : [{ tipo: 'engram', id: 412, titulo: 'Docker sin egress', fecha: '2026-09-18', proyecto: 'acme' }]),
  ]
  return [
    sinEngram ? '_Engram no está disponible ahora; te contesto solo con las sesiones._\n' : '',
    'El entorno local de la tienda lo levantamos el **1 de octubre** con el `compose.local` y un override de límites de RAM, porque con los valores por defecto el contenedor de PHP se moría al compilar.',
    '',
    'Lo que trabó al principio fue que los contenedores no salían a internet: el host tenía el reenvío de red apagado. Se arregló prendiéndolo y reiniciando Docker; no hizo falta tocar la imagen.',
    '',
    'Una diferencia entre fuentes: la sesión del 1 oct dice 4 GB para PHP y la del 2 oct lo bajó a **3 GB**. La más nueva es la del 2.',
    '',
    '```fuentes',
    JSON.stringify(fuentes),
    '```',
  ].join('\n')
}

const CITAS: Record<string, string> = {
  [`${SID}:128`]: 'Listo, quedó arriba. Pasos: 1) docker compose -f compose.local.yml up -d; 2) override de memoria (php 4g, mysql 2g); 3) bajé db y mailhog de api porque chocaban los puertos 3306 y 8025. La password de la base quedó en «oculto».',
  [`${SID2}:42`]: 'Bajé el límite de PHP a 3g: con 4g la notebook se quedaba sin memoria cuando también corría el categorizador. Con 3g compila igual, tarda unos segundos más.',
  'e:412': 'Docker sin egress: net.ipv4.ip_forward=0 en el host bloquea la salida de todos los contenedores. Solución: sysctl -w net.ipv4.ip_forward=1 y reiniciar docker.',
}

/** Mock de memoria: índice con 93 sesiones; con ?falla=engram, Engram aparece caído. */
export function createMockMemoria(): Pick<Api, 'getMemoriaEstado' | 'reindexarMemoria' | 'borrarMemoria' | 'getMemoriaCita'> {
  let estado: MemoriaEstado = {
    habilitada: true,
    indexados: 93,
    turnos: 5412,
    tamano_mb: 24.3,
    ultima_actualizacion: new Date(Date.now() - 2 * 60_000).toISOString(),
    actualizando: false,
    engram: engramCaido() ? 'caido' : 'ok',
  }
  let ultimoReindex = 0
  return {
    async getMemoriaEstado() {
      await sleep(260)
      return { ...estado }
    },
    async reindexarMemoria() {
      await sleep(300)
      if (Date.now() - ultimoReindex < 600_000) throw new ApiError(429, 'Ya se reindexó hace poco', 600)
      ultimoReindex = Date.now()
      estado = { ...estado, actualizando: true, indexados: 0, turnos: 0, tamano_mb: 0 }
      setTimeout(() => (estado = { ...estado, actualizando: false, indexados: 93, turnos: 5412, tamano_mb: 24.3, ultima_actualizacion: new Date().toISOString() }), 4000)
    },
    async borrarMemoria() {
      await sleep(300)
      estado = { ...estado, indexados: 0, turnos: 0, tamano_mb: 0, ultima_actualizacion: null }
    },
    async getMemoriaCita(ref) {
      await sleep(450)
      if (ref.tipo === 'engram') {
        if (engramCaido() || !CITAS[`e:${ref.id}`]) throw new ApiError(404, 'no encontrada')
        return { tipo: 'engram', id: ref.id, texto: CITAS[`e:${ref.id}`] }
      }
      const texto = CITAS[`${ref.session_id}:${ref.turno}`]
      if (!texto) throw new ApiError(404, 'no encontrada')
      const titulo = ref.session_id === SID ? 'Entorno local Tienda' : 'Límites de RAM en compose'
      return { tipo: 'sesion', session_id: ref.session_id, turno: ref.turno, titulo, fecha: ref.session_id === SID ? '2026-10-01' : '2026-10-02', rol: 'claude', texto }
    },
  }
}
