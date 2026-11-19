/** Example ```diagrama blocks for the demo: one architecture with groups and a small one. */

export const DIAGRAMA_ARQ = {
  titulo: 'Cómo te llegan los avisos',
  resumen: 'Quién habla con quién desde que Claude termina hasta que suena tu celu',
  grupos: [
    { id: 'compu', nombre: 'Tu compu', color: 'azul' },
    { id: 'nube', nombre: 'Afuera', color: 'violeta' },
  ],
  nodos: [
    { id: 'claude', nombre: 'Claude', icono: '🤖', tipo: 'app', grupo: 'compu', detalle: 'Trabaja en tus proyectos y avisa cuando termina o cuando necesita algo tuyo.' },
    { id: 'herdr', nombre: 'Terminales', icono: '🗂️', tipo: 'servicio', grupo: 'compu', detalle: 'Organiza las sesiones en pestañas, así sabés qué está haciendo cada una.' },
    { id: 'orq', nombre: 'Colmena', icono: '🐝', tipo: 'servicio', grupo: 'compu', detalle: 'Junta todo lo que pasa en las sesiones y decide cuándo vale la pena avisarte.' },
    { id: 'bib', nombre: 'Biblioteca', icono: '📚', tipo: 'datos', grupo: 'compu', detalle: 'Guarda las páginas, imágenes y diagramas que fueron armando las sesiones.' },
    { id: 'push', nombre: 'Servicio de avisos', icono: '📮', tipo: 'externo', grupo: 'nube', detalle: 'El servicio del navegador que entrega el aviso aunque tengas la app cerrada.' },
    { id: 'celu', nombre: 'Tu celu', icono: '📱', tipo: 'app', grupo: 'nube', detalle: 'Muestra el aviso y abre la sesión cuando lo tocás.' },
    { id: 'vos', nombre: 'Vos', icono: '🙂', tipo: 'persona', detalle: 'Leés el aviso y respondés desde donde estés.' },
    { id: 'nota', nombre: 'Si la app está abierta, el aviso aparece adentro', tipo: 'nota' },
  ],
  conexiones: [
    { de: 'claude', a: 'herdr', texto: 'cuenta que terminó' },
    { de: 'herdr', a: 'orq', texto: 'pasa el estado' },
    { de: 'claude', a: 'bib', texto: 'publica lo que armó', tipo: 'datos' },
    { de: 'orq', a: 'bib', texto: 'lo ordena', tipo: 'datos' },
    { de: 'orq', a: 'push', texto: 'manda el aviso' },
    { de: 'push', a: 'celu', texto: 'lo entrega' },
    { de: 'celu', a: 'vos', texto: 'te muestra el aviso' },
    { de: 'vos', a: 'orq', texto: 'respondés', tipo: 'respuesta' },
    { de: 'celu', a: 'nota' },
  ],
  notas: ['Los avisos se apagan desde Ajustes', 'Nada de esto sale de tu red salvo el aviso al celu'],
}

export const DIAGRAMA_CHICO = {
  titulo: 'Dónde vive cada cosa',
  nodos: [
    { id: 'app', nombre: 'La app', icono: '📱', tipo: 'app', detalle: 'Lo que ves en el celu y en la compu.' },
    { id: 'srv', nombre: 'El servidor', icono: '⚙️', tipo: 'servicio', detalle: 'Corre en tu compu y arma todo lo que la app muestra.' },
    { id: 'db', nombre: 'Tus datos', icono: '🗄️', tipo: 'datos', detalle: 'Lo que se guarda para que no se pierda al reiniciar.' },
  ],
  conexiones: [
    { de: 'app', a: 'srv', texto: 'pide' },
    { de: 'srv', a: 'db', texto: 'guarda y lee', tipo: 'datos' },
    { de: 'srv', a: 'app', texto: 'responde', tipo: 'respuesta' },
  ],
}
