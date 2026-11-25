/** Nombre y para qué sirve cada ícono de la barra: los usan el cartel rápido y el menú ⋯ del celu. */
export const ACCIONES_BARRA = {
  ajustes: { nombre: 'Ajustes', desc: 'Apariencia, avisos, permisos y atajos' },
  entornos: { nombre: 'Entornos', desc: 'Tiendas y servicios de la notebook' },
  kit: { nombre: 'Kit', desc: 'Reglas, skills y hooks de Claude' },
  tareas: { nombre: 'Tareas programadas', desc: 'Pedidos que corren solos a su hora' },
  limpiar: { nombre: 'Limpiar sesiones', desc: 'Cierra las que están quietas, con tu confirmación' },
  salir: { nombre: 'Salir de Colmena', desc: 'En todos tus dispositivos; pide el PIN de nuevo' },
  avisos: { nombre: 'Avisos', desc: 'Lo que pidieron o terminaron las sesiones' },
  tema: { desc: 'Cambia los colores de la app' },
  conexion: { desc: 'Conexión en vivo con la notebook' },
} as const

export type Cartel = { nombre: string; desc: string }
