export const DIAGRAMA_MENSAJE = {
  titulo: 'Cómo te llega un mensaje mío',
  resumen: 'Desde que termino de escribir hasta que lo ves en el celu',
  tipo: 'secuencia',
  actores: [
    { id: 'claude', nombre: 'Claude', icono: '🤖' },
    { id: 'herdr', nombre: 'Terminales', icono: '🖥️' },
    { id: 'orq', nombre: 'Colmena', icono: '🐝' },
    { id: 'ts', nombre: 'Tailscale', icono: '🔒' },
    { id: 'cel', nombre: 'Tu celu', icono: '📱' },
  ],
  pasos: [
    { de: 'claude', texto: 'Escribe la respuesta en el transcript', detalle: 'Cada mensaje queda como una línea en el .jsonl de la sesión', tipo: 'evento' },
    { de: 'herdr', a: 'orq', texto: 'Avisa que la sesión cambió de estado', detalle: "Pasa de 'trabajando' a 'idle' por el socket de eventos", datos: '{pane, status: idle}', tipo: 'llamada' },
    { de: 'orq', texto: 'Lee el transcript y arma el tablero', detalle: 'Saca el último mensaje, detecta tarjetas de opciones y diagramas', tipo: 'evento' },
    { de: 'orq', a: 'ts', texto: 'Manda la notificación push', detalle: 'Web Push firmado con VAPID; sale aunque tengas la app cerrada', tipo: 'llamada' },
    { de: 'ts', a: 'cel', texto: "Te llega 'terminó'", tipo: 'respuesta' },
    { de: 'cel', a: 'orq', texto: 'Abrís la app y pide el chat', detalle: 'Viaja con tu cookie de sesión por el túnel privado', datos: 'GET /api/sessions/…/transcript', tipo: 'llamada' },
    { de: 'orq', a: 'cel', texto: 'Devuelve los mensajes', detalle: 'La app dibuja el texto, las tarjetas y este diagrama', tipo: 'respuesta' },
    { de: 'cel', a: 'orq', texto: 'Si la cookie venció, pide el PIN', tipo: 'error' },
  ],
  notas: ['Todo pasa dentro de tu red de Tailscale, nada sale a internet', 'Si hay versión nueva, la app se recarga sola'],
}

export const DIAGRAMA_BIFE = {
  titulo: 'Cocinar un bife',
  resumen: 'Vuelta y vuelta, con control del punto',
  tipo: 'proceso',
  pasos: [
    { id: 'p1', texto: 'Sacar la carne de la heladera', duracion: '20 min', icono: '🥩', detalle: 'Que llegue a temperatura ambiente' },
    { id: 'p2', texto: 'Calentar bien la plancha', duracion: '5 min', icono: '🔥' },
    { id: 'p3', texto: 'Sellar de un lado', duracion: '3 min', icono: '♨️' },
    { id: 'p4', texto: 'Dar vuelta y revisar', decision: { pregunta: '¿Está en el punto que querés?', si: 'p5', no: 'p3' } },
    { id: 'p5', texto: 'Dejar descansar', duracion: '5 min', icono: '😌' },
    { id: 'p6', texto: 'Sal gruesa y a la mesa', icono: '🧂' },
  ],
}

export const DIAGRAMA_MENSAJE_LLANO = {
  titulo: 'Cómo te llega un mensaje mío (en simple)',
  resumen: 'De que termino de escribir a que lo ves en tu celu',
  tipo: 'secuencia',
  actores: [
    { id: 'claude', nombre: 'Claude', icono: '🤖' },
    { id: 'compu', nombre: 'La compu', icono: '🖥️' },
    { id: 'orq', nombre: 'Colmena', icono: '🐝' },
    { id: 'celu', nombre: 'Tu celu', icono: '📱' },
  ],
  pasos: [
    { de: 'claude', texto: 'Claude termina de escribir su respuesta', detalle: 'Queda guardada en la compu, igual que un chat', tipo: 'evento' },
    { de: 'compu', a: 'orq', texto: 'La compu le avisa a Colmena que Claude terminó', detalle: 'Así Colmena se entera al instante, sin estar preguntando', tipo: 'llamada' },
    { de: 'orq', texto: 'Colmena lee la respuesta y la prepara', detalle: 'Separa el texto de las tarjetas y de los dibujos como este', tipo: 'evento' },
    { de: 'orq', a: 'celu', texto: 'Colmena le manda un aviso a tu celu', detalle: 'Te llega aunque tengas la app cerrada, para que sepas que te toca', tipo: 'llamada' },
    { de: 'celu', a: 'orq', texto: 'Abrís la app y tu celu pide la conversación', detalle: 'Viaja por tu red privada, nadie más la ve', tipo: 'llamada' },
    { de: 'orq', a: 'celu', texto: 'Colmena le devuelve la conversación a tu celu', detalle: 'Y ahí la ves en pantalla, con este mismo dibujo', tipo: 'respuesta' },
    { de: 'celu', a: 'orq', texto: 'Si pasó mucho tiempo, tu celu no logra entrar', detalle: 'Por seguridad te pide el PIN otra vez', tipo: 'error' },
  ],
  notas: ['Todo viaja por tu red privada: nada sale a internet', 'Si hay una versión nueva de la app, se actualiza sola'],
}

export const DIAGRAMA_LARGO = {
  titulo: 'Despliegue en 20 pasos',
  resumen: 'Un diagrama largo para ver cómo serpentea',
  tipo: 'proceso',
  pasos: [
    { id: 'l1', texto: 'Pedís el despliegue', icono: '🚀' },
    { id: 'l2', texto: 'Se valida el pedido', icono: '✅' },
    { id: 'l3', texto: 'Se arma la imagen', icono: '📦' },
    { id: 'l4', texto: 'Corren los tests', icono: '🧪', detalle: 'Esto toma un rato y conviene mirar que todo siga verde antes de seguir' },
    { id: 'l5', texto: 'Se firma la imagen', icono: '🔏' },
    { id: 'l6', texto: 'Sube al registro', icono: '☁️' },
    { id: 'l7', texto: 'Se prepara la base', icono: '🗄️' },
    { id: 'l8', texto: 'Se aplican migraciones', icono: '🧬', detalle: 'Esto toma un rato y conviene mirar que todo siga verde antes de seguir' },
    { id: 'l9', texto: 'Arranca el canario', icono: '🐤' },
    { id: 'l10', texto: 'Se mide la salud', icono: '🩺' },
    { id: 'l11', texto: 'Se revisan errores', icono: '🐞' },
    { id: 'l12', texto: 'Sube el tráfico al 25%', icono: '📈', detalle: 'Esto toma un rato y conviene mirar que todo siga verde antes de seguir' },
    { id: 'l13', texto: 'Se mide otra vez', icono: '📏' },
    { id: 'l14', texto: 'Sube el tráfico al 100%', icono: '🌊' },
    { id: 'l15', texto: 'Se apaga la versión vieja', icono: '🪦' },
    { id: 'l16', texto: 'Se limpia la caché', icono: '🧹', detalle: 'Esto toma un rato y conviene mirar que todo siga verde antes de seguir' },
    { id: 'l17', texto: 'Se avisa al equipo', icono: '📣' },
    { id: 'l18', texto: 'Se anota en el registro', icono: '📝' },
    { id: 'l19', texto: 'Se archiva el build', icono: '🗃️' },
    { id: 'l20', texto: 'Listo, en producción', icono: '🎉', detalle: 'Esto toma un rato y conviene mirar que todo siga verde antes de seguir' },
  ],
}
