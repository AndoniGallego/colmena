import { DIAGRAMA_ARQ, DIAGRAMA_CHICO } from './diagramas'
import { DIAGRAMA_BIFE, DIAGRAMA_MENSAJE, DIAGRAMA_MENSAJE_LLANO } from './diagramasReales'
import { matchesFilters } from '../lib/biblioteca'
import { ApiError, type LibFilters, type LibItem, type LibKind, type LibListing, type LibSession } from '../api/types'

const hoursAgo = (h: number) => new Date(Date.now() - h * 3_600_000).toISOString()
const uri = (mime: string, body: string) => `data:${mime};charset=utf-8,${encodeURIComponent(body)}`

const PAGE = (titulo: string, hue: number) =>
  uri(
    'text/html',
    `<!doctype html><html><head><meta charset="utf-8"><title>${titulo}</title><style>
body{margin:0;font:16px system-ui;background:hsl(${hue} 40% 96%);color:#222;display:grid;place-items:center;min-height:100vh}
.card{background:#fff;border-radius:18px;padding:32px 40px;box-shadow:0 12px 40px hsl(${hue} 40% 40% / .18);max-width:520px}
h1{margin:0 0 8px;font-size:28px;color:hsl(${hue} 60% 38%)}.bar{height:10px;border-radius:6px;background:hsl(${hue} 70% 60%);margin:18px 0;width:0;animation:g 1.4s ease forwards}
@keyframes g{to{width:100%}}button{border:0;background:hsl(${hue} 60% 42%);color:#fff;padding:10px 18px;border-radius:10px;font:inherit;cursor:pointer}
</style></head><body><div class="card"><h1>${titulo}</h1><p>Página de ejemplo generada por una sesión.</p><div class="bar"></div>
<button onclick="this.textContent='Listo '+new Date().toLocaleTimeString()">Probar</button></div></body></html>`,
  )

const SVG = (hue: number, label: string) =>
  uri(
    'image/svg+xml',
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 400"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="hsl(${hue} 70% 62%)"/><stop offset="1" stop-color="hsl(${hue + 50} 70% 45%)"/></linearGradient></defs><rect width="640" height="400" fill="url(#g)"/><circle cx="470" cy="130" r="70" fill="#fff" opacity=".25"/><text x="40" y="350" font-family="system-ui" font-size="44" fill="#fff">${label}</text></svg>`,
  )

const GIF = uri(
  'image/svg+xml',
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200"><rect width="320" height="200" fill="#1c2430"/><circle r="22" cy="100" fill="#f0b429"><animate attributeName="cx" values="40;280;40" dur="2.4s" repeatCount="indefinite"/></circle></svg>`,
)

const DIAGRAMA_LOGIN = JSON.stringify({
  titulo: 'Login con SSO',
  tipo: 'proceso',
  pasos: [
    { texto: 'El usuario abre el módulo y toca Ingresar' },
    { texto: 'La tienda redirige al IdP con state firmado' },
    { texto: 'El IdP vuelve al callback con el código' },
    { texto: 'Se crea la sesión y se vuelve a return_to' },
  ],
})

const MD = '# Notas del handoff\n\nQuedó pendiente:\n\n- Tests contra Keycloak local\n- Revisar `return_to` en el callback\n\n```php\n$state = sign($returnTo);\n```\n'

let n = 0
const base = (kind: LibKind, over: Partial<LibItem>): LibItem => ({
  id: String(++n).padStart(32, '0'),
  kind,
  source: 'SendUserFile',
  session_id: 'mock-wC-p1',
  session_titulo: 'Módulo Acme en monorepo ps9',
  project: 'ps9',
  subagent: '',
  ts: hoursAgo(1),
  title: '',
  description: '',
  caption: '',
  nombre: '',
  donde: '',
  exists: true,
  copia: true,
  servible: true,
  motivo: '',
  size: 18_000,
  mime: '',
  url: '',
  version: 1,
  versions: [],
  diagrama_raw: '',
  src: '',
  ...over,
})

const SESS = {
  a: { session_id: 'mock-wC-p1', session_titulo: 'Módulo Acme en monorepo ps9' },
  b: { session_id: 'mock-w1-p1', session_titulo: 'Orquestador de sesiones web con chat integrado' },
  c: { session_id: 'mock-w8-p2', session_titulo: 'Revisión de componentes Grove' },
}

export const MOCK_LIB_IDS = {
  html: '00000000000000000000000000000001',
  image: '00000000000000000000000000000003',
  secuencia: '00000000000000000000000000000009',
  mensaje: '00000000000000000000000000000015',
  bife: '00000000000000000000000000000016',
  llano: '00000000000000000000000000000017',
  diagramaArq: '00000000000000000000000000000018',
  diagramaChico: '00000000000000000000000000000019',
  captura1: '00000000000000000000000000000020',
  captura2: '00000000000000000000000000000021',
  captura3: '00000000000000000000000000000022',
  captura4: '00000000000000000000000000000023',
  captura5: '00000000000000000000000000000024',
  captura6: '00000000000000000000000000000025',
  captura7: '00000000000000000000000000000026',
}

const CAPTURA_SRC = SVG(180, 'Captura')

const PRUEBAS_EJEMPLO = JSON.stringify({
  titulo: 'Checkout con tarjeta',
  resumen: 'Se probó el pago de punta a punta en la tienda local.',
  casos: [
    { nombre: 'Pagar con una tarjeta válida', resultado: 'ok' },
    { nombre: 'Pagar con una tarjeta rechazada', resultado: 'falla', detalle: 'No aparece el mensaje de error al rechazar el pago.' },
    { nombre: 'Pagar en cuotas', resultado: 'omitida', detalle: 'Falta configurar las cuotas en la tienda.' },
  ],
})

function build(): LibItem[] {
  n = 0
  return [
    base('html', { ...SESS.a, source: 'Artifact', ts: hoursAgo(0.3), title: 'Tablero de reservas', description: 'Resumen de reservas por tienda', nombre: 'reservas.html', url: 'https://claude.ai/artifact/AbCdEf123456', version: 3, versions: [{ version: 3, ts: hoursAgo(0.3) }, { version: 2, ts: hoursAgo(2) }, { version: 1, ts: hoursAgo(5) }], src: PAGE('Tablero de reservas', 205) }),
    base('html', { ...SESS.b, source: 'Artifact', ts: hoursAgo(2), title: 'Mapa de procesos', nombre: 'procesos.html', url: 'https://claude.ai/artifact/ZxCvBn987654', src: PAGE('Mapa de procesos', 150) }),
    base('image', { ...SESS.b, ts: hoursAgo(2.5), title: 'Captura del checkout', caption: 'Error de expiración de token', nombre: 'checkout.png', mime: 'image/png', size: 220_000, src: SVG(12, 'Checkout') }),
    base('svg', { ...SESS.a, ts: hoursAgo(4), title: 'Diagrama de módulos', nombre: 'modulos.svg', mime: 'image/svg+xml', src: SVG(260, 'Módulos') }),
    base('gif', { ...SESS.c, ts: hoursAgo(6), title: 'Animación del carrusel', nombre: 'carrusel.gif', mime: 'image/gif', size: 900_000, src: GIF }),
    base('pdf', { ...SESS.c, ts: hoursAgo(7), title: 'Reporte de componentes', nombre: 'grove-gaps.pdf', mime: 'application/pdf', size: 1_400_000, servible: false, motivo: 'Sin vista previa en la demo' }),
    base('video', { ...SESS.b, ts: hoursAgo(26), title: 'Grabación del chat', nombre: 'chat.webm', mime: 'video/webm', size: 4_800_000, servible: false, motivo: 'Sin vista previa en la demo' }),
    base('text', { ...SESS.a, ts: hoursAgo(27), title: 'Handoff de la sesión', nombre: 'handoff.md', mime: 'text/markdown', size: 800 }),
    base('diagrama', { ...SESS.a, source: 'chat', ts: hoursAgo(28), title: 'Login con SSO', diagrama_raw: DIAGRAMA_LOGIN, servible: false }),
    base('pruebas', { ...SESS.a, source: 'pruebas', ts: hoursAgo(0.15), title: 'Checkout con tarjeta', description: '1 ok · 1 falla · 1 omitida', servible: false, mime: 'application/json', pruebas_raw: PRUEBAS_EJEMPLO, evidencias: {} }),
    base('remoto', { ...SESS.c, source: 'Artifact', ts: hoursAgo(50), title: 'Dashboard de ventas', url: 'https://claude.ai/artifact/QwErTy135790', exists: false, copia: false, servible: false, motivo: 'La página quedó solo en claude.ai' }),
    base('html', { ...SESS.b, source: 'Artifact', ts: hoursAgo(52), title: 'Página borrada', nombre: 'vieja.html', exists: false, copia: false, servible: false, motivo: 'El archivo ya no existe' }),
    base('image', { ...SESS.c, ts: hoursAgo(75), title: 'Paleta de colores', nombre: 'paleta.png', mime: 'image/png', src: SVG(320, 'Paleta') }),
    base('html', { ...SESS.a, source: 'Artifact', ts: hoursAgo(98), title: 'Calculadora de cuotas', nombre: 'cuotas.html', src: PAGE('Calculadora de cuotas', 30) }),
    base('diagrama', { ...SESS.b, source: 'chat', ts: hoursAgo(120), title: 'Pago con tarjeta', diagrama_raw: DIAGRAMA_LOGIN.replace('Login con SSO', 'Pago con tarjeta'), servible: false }),
    base('diagrama', { ...SESS.a, source: 'chat', ts: hoursAgo(0.1), title: DIAGRAMA_MENSAJE.titulo, diagrama_raw: JSON.stringify(DIAGRAMA_MENSAJE), servible: false }),
    base('diagrama', { ...SESS.a, source: 'chat', ts: hoursAgo(0.1), title: DIAGRAMA_BIFE.titulo, diagrama_raw: JSON.stringify(DIAGRAMA_BIFE), servible: false }),
    base('diagrama', { ...SESS.a, source: 'chat', ts: hoursAgo(0.1), title: DIAGRAMA_MENSAJE_LLANO.titulo, diagrama_raw: JSON.stringify(DIAGRAMA_MENSAJE_LLANO), servible: false }),
    base('diagrama', { ...SESS.a, source: 'chat', ts: hoursAgo(0.05), title: DIAGRAMA_ARQ.titulo, diagrama_raw: JSON.stringify(DIAGRAMA_ARQ), servible: false }),
    base('diagrama', { ...SESS.a, source: 'chat', ts: hoursAgo(0.05), title: DIAGRAMA_CHICO.titulo, diagrama_raw: JSON.stringify(DIAGRAMA_CHICO), servible: false }),
    base('image', { id: MOCK_LIB_IDS.captura1, ...SESS.a, source: 'captura', ts: hoursAgo(0.2), title: 'Captura del navegador', nombre: 'pantalla.png', mime: 'image/png', src: CAPTURA_SRC }),
    base('image', { id: MOCK_LIB_IDS.captura2, ...SESS.a, source: 'captura', ts: hoursAgo(0.2), title: 'Captura del navegador', nombre: 'pantalla-2.png', mime: 'image/png', src: CAPTURA_SRC }),
    base('image', { id: MOCK_LIB_IDS.captura3, ...SESS.a, source: 'captura', ts: hoursAgo(0.2), title: 'Captura del navegador', nombre: 'pantalla-3.png', mime: 'image/png', src: CAPTURA_SRC }),
    base('image', { id: MOCK_LIB_IDS.captura4, ...SESS.a, source: 'captura', ts: hoursAgo(0.2), title: 'Captura del navegador', nombre: 'pantalla-4.png', mime: 'image/png', src: CAPTURA_SRC }),
    base('image', { id: MOCK_LIB_IDS.captura5, ...SESS.a, source: 'captura', ts: hoursAgo(0.2), title: 'Captura del navegador', nombre: 'pantalla-5.png', mime: 'image/png', src: CAPTURA_SRC }),
    base('image', { id: MOCK_LIB_IDS.captura6, ...SESS.a, source: 'captura', ts: hoursAgo(0.2), title: 'Captura del navegador', nombre: 'pantalla-6.png', mime: 'image/png', src: CAPTURA_SRC }),
    base('image', { id: MOCK_LIB_IDS.captura7, ...SESS.a, source: 'captura', ts: hoursAgo(0.2), title: 'Captura del navegador', nombre: 'pantalla-7.png', mime: 'image/png', src: CAPTURA_SRC }),
  ]
}

export function createMockLibrary() {
  const items = build()
  const find = (id: string) => items.find((i) => i.id === id)
  return {
    items,
    list(f: LibFilters, cursor?: string | null, limit = 60): LibListing {
      const all = items.filter((i) => matchesFilters(i, f))
      const start = cursor ? Number(cursor) || 0 : 0
      const next = start + limit
      return { items: all.slice(start, next), cursor: next < all.length ? String(next) : null, indexando: false, total: all.length }
    },
    item(id: string, f?: LibFilters): LibItem {
      const hit = find(id)
      if (!hit) throw new ApiError(404, 'No existe')
      const all = f ? items.filter((i) => matchesFilters(i, f)) : items
      const at = all.findIndex((i) => i.id === id)
      return { ...hit, vecinos: { anterior: all[at - 1]?.id ?? null, siguiente: all[at + 1]?.id ?? null } }
    },
    sessions(): LibSession[] {
      return Object.values(SESS).map((s) => {
        const own = items.filter((i) => i.session_id === s.session_id)
        return { session_id: s.session_id, titulo: s.session_titulo, proyecto: 'ps9', n: own.length, ultimo_ts: own[0]?.ts ?? '' }
      })
    },
    quitar(ids: string[]): number {
      const before = items.length
      for (const id of ids) {
        const at = items.findIndex((i) => i.id === id)
        if (at >= 0) items.splice(at, 1)
      }
      return before - items.length
    },
    text(id: string): string {
      const hit = find(id)
      if (!hit || hit.kind !== 'text') throw new ApiError(404, 'No existe')
      return MD
    },
  }
}
