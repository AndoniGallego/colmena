import { ApiError } from '../api/types'
import type { Mr, MrDetalle, MrEvento, MrJob, MrPersona, MrsApi, MrsListado, PipeEstado } from '../api/mrsApi'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))
const PIN = '1234'
const YO: MrPersona = { username: 'ana.ejemplo', nombre: 'Ana Ejemplo' }
const EQUIPO: MrPersona[] = [
  { username: 'tomas.diaz', nombre: 'Tomás Díaz' },
  { username: 'valeria.gomez', nombre: 'Valeria Gómez' },
  { username: 'lucia.perez', nombre: 'Lucía Pérez' },
  { username: 'diego.ramos', nombre: 'Diego Ramos' },
  { username: 'camila.torres', nombre: 'Camila Torres' },
]
const persona = (u: string) => EQUIPO.find((p) => p.username === u) ?? YO
const sha = (n: number) => n.toString(16).padStart(40, 'a')
const hace = (min: number) => new Date(Date.now() - min * 60_000).toISOString()

function mk(o: Partial<Mr> & { pid: number; iid: number; repo: string }): Mr {
  const { pid, iid, repo, ...rest } = o
  return {
    ref: `${pid}:${iid}`,
    project_id: pid,
    iid,
    repo: `mi-grupo/development/${repo}`,
    repo_corto: repo,
    titulo: '',
    rama: 'feature/x',
    target: 'main',
    rol: 'autor',
    autor: YO,
    draft: false,
    conflictos: false,
    estado_merge: 'mergeable',
    puede_mergear: true,
    sha: sha(pid * 1000 + iid),
    pipeline: { estado: 'ok', id: pid * 10_000 + iid, url: 'https://gitlab.com/mi-grupo/development/x/-/pipelines/1' },
    aprobaciones: { dadas: 0, requeridas: 1, faltan: 1, por: [], yo: false, puedo: false },
    reviewers: [],
    hilos_sin_resolver: 0,
    comentarios_nuevos: 0,
    url: `https://gitlab.com/mi-grupo/development/${repo}/-/merge_requests/${iid}`,
    actualizado: hace(10),
    creado: hace(60 * 24 * 3),
    pausado: false,
    ...rest,
  }
}

function seed(): Mr[] {
  return [
    mk({ pid: 101, iid: 412, repo: 'tienda', titulo: 'feat: checkout con cuotas sin interés', rama: 'feature/DEMO-88', target: 'develop', pipeline: { estado: 'fallo', id: 9_912, url: '' }, reviewers: [persona('tomas.diaz')], hilos_sin_resolver: 2, comentarios_nuevos: 1, actualizado: hace(4) }),
    mk({ pid: 101, iid: 409, repo: 'tienda', titulo: 'fix: login federado respeta return_to', rama: 'feature/DEMO-81', target: 'develop', pipeline: { estado: 'corriendo', id: 9_901, url: '' }, reviewers: [persona('valeria.gomez')], actualizado: hace(18) }),
    mk({ pid: 230, iid: 77, repo: 'kit', titulo: 'chore: mover el kit a innovacion/kit', rama: 'feature/kit-remote', reviewers: [persona('diego.ramos')], aprobaciones: { dadas: 1, requeridas: 1, faltan: 0, por: [persona('diego.ramos')], yo: false, puedo: false }, actualizado: hace(55) }),
    mk({ pid: 140, iid: 31, repo: 'web', titulo: 'Draft: feat: carrusel de recomendaciones IA', rama: 'feature/DEMO-98', draft: true, conflictos: true, pipeline: { estado: 'sin', id: 0, url: '' }, actualizado: hace(300), pausado: true }),
    mk({ pid: 160, iid: 533, repo: 'datos', titulo: 'DEMO-101: endpoint GET /carousel/recommendations/:id para el carrusel de recomendaciones de la home (proveedor simulado + servicio de modelos)', rama: 'feature/DEMO-101-recomendaciones-carrusel-home-proveedor-modelos-red-privada', target: 'master', rol: 'revisor', autor: persona('lucia.perez'), reviewers: [YO, persona('diego.ramos')], puede_mergear: false, aprobaciones: { dadas: 0, requeridas: 1, faltan: 1, por: [], yo: false, puedo: true }, hilos_sin_resolver: 1, comentarios_nuevos: 2, actualizado: hace(12) }),
    mk({ pid: 150, iid: 205, repo: 'api', titulo: 'fix: categorizador sigue el redirect a https', rama: 'feature/DEMO-97', rol: 'revisor', autor: persona('lucia.perez'), reviewers: [YO], puede_mergear: false, aprobaciones: { dadas: 0, requeridas: 1, faltan: 1, por: [], yo: false, puedo: true }, hilos_sin_resolver: 1, actualizado: hace(25) }),
    mk({ pid: 120, iid: 88, repo: 'docs', titulo: 'feat: reservas de stock con lock optimista', rama: 'feature/DEMO-99', rol: 'revisor', autor: persona('camila.torres'), reviewers: [YO, persona('tomas.diaz')], pipeline: { estado: 'ok', id: 7_788, url: '' }, aprobaciones: { dadas: 1, requeridas: 2, faltan: 1, por: [YO], yo: true, puedo: true }, actualizado: hace(130) }),
  ]
}

const JOBS = (estado: PipeEstado): MrJob[] => {
  const base: [string, string, PipeEstado][] = [
    ['lint', 'test', 'ok'],
    ['phpunit', 'test', estado === 'fallo' ? 'fallo' : estado === 'corriendo' ? 'corriendo' : 'ok'],
    ['e2e', 'test', estado === 'corriendo' ? 'corriendo' : 'ok'],
    ['build-image', 'build', estado === 'ok' ? 'ok' : 'cancelado'],
    ['deploy-uat', 'deploy', 'manual'],
  ]
  return base.map(([nombre, etapa, e], i) => ({
    id: 700 + i,
    nombre,
    etapa,
    estado: e,
    status: e === 'fallo' ? 'failed' : e === 'ok' ? 'success' : e,
    url: '',
    duracion: 40 + i * 37,
    reintentable: e === 'fallo' || e === 'cancelado',
    permitido_fallar: false,
  }))
}

const DIFF = `@@ -12,7 +12,11 @@ class Cuotas
     public function plan(Cart $cart): array
     {
-        return $this->gateway->cuotas($cart->total());
+        $total = $cart->total();
+        if ($total <= 0) {
+            return [];
+        }
+        return $this->gateway->cuotas($total, self::SIN_INTERES);
     }`

// Parecido a un MR real con descripción larga, Revisor automático y mucha actividad de sistema (texto parafraseado).
const DESC_LARGA = `> ⚠️ **Pendiente:** probar contra el endpoint real de UAT. El contrato ya está cerrado con @valeria.gomez (ver !495 y #12).

## Resumen
- Nuevo endpoint \`GET /carousel/recommendations/:id?product_ids=<csv>\` para el carrusel de recomendaciones de la home.
- La config del bloque (\`requested_count\`, \`max_to_return\`, \`title\`) se lee de la vista \`v_carousel_recommendations_with_a_really_long_identifier_name\` como **override opcional**; si no hay vista se usan defaults (10 / 5 / \`''\`).
- Cache de ids: \`ids:HOME:<requestedCount>:<productIdsSortedAndJoinedWithCommasWithoutSpaces>\` con TTL de 900 s.
- Docs: https://gitlab.com/mi-grupo/stores/servicios/datos/-/blob/feature/DEMO-101-recomendaciones-carrusel-home-proveedor-modelos-red-privada/specs/modules/carousel-manager/recommendations.md

## Cambios
### Endpoint
- \`start/routes.js\`: ruta nueva **antes** de \`carousel/:type/:id\` (si no, la genérica la captura y responde 500).
- \`CarouselController.showRecommended()\`: \`400\` input inválido, \`404\` si la tienda no corresponde, \`200\` en todo lo demás.

| Caso | Respuesta | Log |
|---|---|---|
| Vista inexistente (\`ER_NO_SUCH_TABLE\`) | defaults | \`info config_no_table blockId=1234 correlationId=00000000-0000-4000-8000-000000000000\` |
| Campo inválido | default por campo | \`warn config_field_invalid\` |
| Otro error de BD | defaults | \`error config_db_error\` |

\`\`\`js
const client = new ModelosClient({ region: config.region ?? 'region-demo', credentials: credencialesTemporales({ params: { RoleArn: roleArn, RoleSessionName: 'datos-recomendaciones' } }), maxAttempts: 1 })
\`\`\`

![diagrama de la recomendación](/uploads/0a1b2c3d4e5f/diagrama-recomendaciones.png)

## Test plan
- [x] Tests unitarios (\`test/unit/recommendation*.test.js\`): 125 pass, 0 fail
- [x] E2E contra BD local con provider mock
- [ ] Probar en UAT contra el endpoint real
`

const REVISOR_BOT = `<!-- This is an auto-generated comment by Revisor automático -->
**📐 Maintainability** | **🟡 Minor** | **⚡ Quick win**

**\`@ejemplo/http-cliente\` no está declarada como dependencia.**

El test la importa y apaga \`import/no-extraneous-dependencies\` para esa línea.

<details>
<summary>🔎 Supported by static analysis</summary>

🏁 Script executed:

\`\`\`bash
#!/bin/bash
rg -n '"@ejemplo/http-cliente"' package.json yarn.lock && sed -n '1,120p' test/unit/modelosProviderTransport.test.js | grep -n 'import' | head -50
\`\`\`

Length of output: 3084

</details>

<details>
<summary>🤖 Prompt for AI Agents</summary>

\`\`\`
In test/unit/modelosProviderTransport.test.js around lines 1-15, declare @ejemplo/http-cliente as a devDependency in package.json instead of disabling the lint rule inline; keep the lockfile untouched otherwise.
\`\`\`

</details>

<!-- fingerprinting:demo:0000 -->`

function actividadLarga(): MrEvento[] {
  const bot = { username: 'group_0000000_bot_demo', nombre: 'Revisor automático' }
  const mati = persona('lucia.perez')
  const ev = (id: number, autor: MrPersona, cuerpo: string, min: number): MrEvento => ({ id, autor, cuerpo, fecha: hace(min), mio: autor.username === YO.username })
  return [
    ev(901, mati, 'requested review from @valeria.gomez and @camila.torres', 3000),
    ev(902, mati, 'assigned to @lucia.perez', 2990),
    ev(903, mati, 'mentioned in merge request !495', 2900),
    ev(904, mati, "added 38 commits\n\n<ul><li>1a2b3c4d...5e6f7a8b - 36 commits from branch <code>master</code></li><li>9c8d7e6f - Merge remote-tracking branch &#39;origin/master&#39; into feature/DEMO-101</li></ul>\n\n[Compare with previous version](/mi-grupo/stores/servicios/datos/-/merge_requests/533/diffs?diff_id=1&start_sha=abc)", 2000),
    ev(905, mati, 'changed the description', 1990),
    ev(906, mati, 'requested review from @diego.ramos and removed review request for @camila.torres', 1500),
    ev(907, mati, 'marked this merge request as **ready**', 1400),
    ev(908, bot, 'changed the description', 1300),
    ev(909, bot, 'changed the description', 1290),
    ev(910, mati, 'changed this line in [version 5 of the diff](/mi-grupo/stores/servicios/datos/-/merge_requests/533/diffs?diff_id=2000000001&start_sha=0123456789abcdef0123456789abcdef01234567#fedcba9876543210fedcba9876543210fedcba98_73_0)', 900),
    ev(911, mati, 'mentioned in commit a1b2c3d4e5f60718293a4b5c6d7e8f9012345678', 800),
    ev(912, mati, 'added 1 commit\n\n<ul><li>a1b2c3d4 - chore: atender comentarios de Revisor automático</li></ul>', 790),
    ev(913, mati, 'resolved all threads', 700),
    ev(914, bot, 'resolved all threads', 690),
    ev(915, mati, 'requested review from @ana.ejemplo', 60),
  ]
}

function detalleLargo(m: Mr): MrDetalle {
  const bot = { username: 'group_0000000_bot_demo', nombre: '' }
  return {
    ...structuredClone(m),
    descripcion: DESC_LARGA,
    jobs: JOBS('ok').map((j, i) => (i === 3 ? { ...j, nombre: 'build-and-push-image-datos-recommendations-modelos-red-privada' } : j)),
    hilos: [
      { id: 'cr1', resoluble: true, resuelto: false, archivo: 'test/unit/modelosProviderTransport.test.js', linea: 15, notas: [
        { id: 31, autor: bot, cuerpo: REVISOR_BOT, fecha: hace(600), mio: false },
        { id: 32, autor: persona('lucia.perez'), cuerpo: 'Resuelto en a1b2c3d: los 13 tests del feature se renombraron a \`*.test.js\` y ahora corren con \`yarn test:unit\` (\`node --test test/unit/*.test.js\`: 125 pass, 0 fail). El E2E \`verifyRecomendaciones.js\` mantiene el nombre, igual que los demás \`verify*.js\`.', fecha: hace(500), mio: false },
      ] },
      { id: 'cr2', resoluble: false, resuelto: false, archivo: '', linea: 0, notas: [
        { id: 33, autor: bot, cuerpo: '<!-- review_stack_entry_start -->\n\n**[Review in Change Stack →](https://revisor.example.com/change-stack/gitlab/mi-grupo%2Fstores%2Fservicios%2Fdatos/merge_request/533?scope=gls_demo)**\n\n<!-- review_stack_entry_end -->\n\n**Actionable comments posted: 3**\n\n<details>\n<summary>🪄 Fix comments</summary>\n\nFix all unresolved Revisor automático comments on this Merge request: use the \`@revisor-bot fix comments\` command.\n\n</details>', fecha: hace(650), mio: false },
      ] },
      { id: 'yo1', resoluble: false, resuelto: false, archivo: '', linea: 0, notas: [
        { id: 34, autor: YO, cuerpo: 'Lo miro mañana, @lucia.perez. ¿El cooldown de 30 s aplica también si **Redis** falla?\n\n1. Si cae Redis\n2. Si cae el provider', fecha: hace(30), mio: true },
      ] },
    ],
    actividad: actividadLarga(),
    archivos: [
      { path: 'app/Services/Recommendations/Providers/ModelosRecommendationProvider.js', viejo: '', nuevo: true, borrado: false, renombrado: false, diff: '@@ -0,0 +1,4 @@\n+const { ModelosClient, InvocarCommand } = require(\'@ejemplo/cliente-modelos\') // cliente con credenciales temporales y endpoint por red privada\n+\n+module.exports = class ModelosRecommendationProvider {}\n+', truncado: false },
      ...detalle(mk({ pid: 1, iid: 1, repo: 'x' })).archivos,
    ],
  }
}

function detalle(m: Mr): MrDetalle {
  if (m.ref === '160:533') return detalleLargo(m)
  return {
    ...structuredClone(m),
    descripcion: `Agrega el selector de cuotas en el checkout.\n\n## Cambios\n- Nuevo hook \`displayPaymentTop\` con el plan de cuotas.\n- Tests de la API del gateway con mocks.\n\n## Cómo probar\n1. Carrito con un producto de más de $10.000.\n2. Elegir **3 cuotas sin interés**.`,
    jobs: m.pipeline.id ? JOBS(m.pipeline.estado) : [],
    hilos: m.hilos_sin_resolver
      ? [
          { id: 'h1', resoluble: true, resuelto: false, archivo: 'modules/cuotas/src/Cuotas.php', linea: 16, notas: [
            { id: 1, autor: persona('tomas.diaz'), cuerpo: '¿Qué pasa si el gateway no devuelve planes? Me parece que acá conviene loguear.', fecha: hace(50), mio: false },
            { id: 2, autor: YO, cuerpo: 'Buena, lo agrego.', fecha: hace(40), mio: true },
          ] },
          { id: 'h2', resoluble: true, resuelto: false, archivo: '', linea: 0, notas: [
            { id: 3, autor: persona('tomas.diaz'), cuerpo: 'Falta el bump de versión en composer.json.', fecha: hace(5), mio: false },
          ] },
          { id: 'h3', resoluble: false, resuelto: false, archivo: '', linea: 0, notas: [
            { id: 4, autor: persona('valeria.gomez'), cuerpo: 'Lo pruebo mañana en UAT.', fecha: hace(120), mio: false },
          ] },
        ]
      : [],
    actividad: [
      { id: 801, autor: persona('tomas.diaz'), cuerpo: 'added 1 commit\n\n<ul><li>abc1234 - fix: x</li></ul>', fecha: hace(90), mio: false },
      { id: 802, autor: persona('tomas.diaz'), cuerpo: 'approved this merge request', fecha: hace(80), mio: false },
    ],
    archivos: [
      { path: 'modules/cuotas/src/Cuotas.php', viejo: 'modules/cuotas/src/Cuotas.php', nuevo: false, borrado: false, renombrado: false, diff: DIFF, truncado: false },
      { path: 'modules/cuotas/tests/CuotasTest.php', viejo: '', nuevo: true, borrado: false, renombrado: false, diff: '@@ -0,0 +1,3 @@\n+<?php\n+\n+final class CuotasTest extends TestCase {}', truncado: false },
      { path: 'modules/cuotas/views/old.tpl', viejo: 'modules/cuotas/views/old.tpl', nuevo: false, borrado: true, renombrado: false, diff: '', truncado: false },
    ],
  }
}

export function createMockMrs(): MrsApi {
  let items = seed()
  const sesiones: Record<string, string> = { 'mock-wG-p1': '101:409', 'mock-wC-p1': '101:412', 'mock-wA-p1': '230:77' }
  let failsPin = 0
  const listado = (): MrsListado => ({ items: items.map((m) => structuredClone(m)), error: '', actualizado: Math.floor(Date.now() / 1000), refrescando: false, disponible: true, habilitado: true, sesiones: { ...sesiones } })
  const find = (ref: string) => {
    const m = items.find((x) => x.ref === ref)
    if (!m) throw new ApiError(404, 'Ese MR no está en tu lista')
    return m
  }
  const checkPin = (pin: string) => {
    if (failsPin >= 5) throw new ApiError(429, 'Demasiados intentos', 60)
    if (pin !== PIN) {
      failsPin++
      throw new ApiError(403, 'PIN incorrecto')
    }
    failsPin = 0
  }
  return {
    async listar() {
      await sleep(350)
      return listado()
    },
    async refrescar() {
      await sleep(1100)
      return listado()
    },
    async detalle(ref) {
      await sleep(420)
      return detalle(find(ref))
    },
    async aprobar(ref, si) {
      await sleep(500)
      const m = find(ref)
      m.aprobaciones.yo = si
      m.aprobaciones.por = si ? [...m.aprobaciones.por.filter((p) => p.username !== YO.username), YO] : m.aprobaciones.por.filter((p) => p.username !== YO.username)
      m.aprobaciones.dadas = m.aprobaciones.por.length
      m.aprobaciones.faltan = Math.max(0, m.aprobaciones.requeridas - m.aprobaciones.dadas)
    },
    async comentar(ref) {
      await sleep(500)
      find(ref)
    },
    async reintentar(ref, cual) {
      await sleep(600)
      const m = find(ref)
      if ('pipeline_id' in cual || m.pipeline.estado === 'fallo') m.pipeline.estado = 'corriendo'
    },
    async reviewers(ref, usernames) {
      await sleep(500)
      find(ref).reviewers = usernames.map(persona)
    },
    async draft(ref, draft) {
      await sleep(450)
      const m = find(ref)
      m.draft = draft
      const base = m.titulo.replace(/^draft:\s*/i, '')
      m.titulo = draft ? `Draft: ${base}` : base
    },
    async pausar(ref, si) {
      await sleep(280)
      find(ref).pausado = si
    },
    async pedirActualizar(ref) {
      await sleep(400)
      find(ref)
      if (!Object.values(sesiones).includes(ref)) throw new ApiError(404, 'Ese MR no tiene una sesión abierta')
    },
    async destinos(ref) {
      await sleep(250)
      find(ref)
      const asociada = Object.entries(sesiones).find(([, r]) => r === ref)?.[0] ?? null
      return {
        sugerida: asociada,
        sesiones: Object.keys(sesiones).map((id) => ({ session_id: id, pane_id: 'w1:p1', nombre: `Sesión ${id.slice(0, 8)}`, status: 'idle', carpeta_corta: 'demo/repo', asociada: id === asociada })),
      }
    },
    async jobASesion(ref) {
      await sleep(400)
      find(ref)
    },
    async hiloASesion(ref) {
      await sleep(400)
      find(ref)
    },
    async mergear(ref, pin) {
      await sleep(700)
      checkPin(pin)
      const m = find(ref)
      if (m.conflictos) throw new ApiError(409, 'GitLab no te deja: tiene conflictos')
      items = items.filter((x) => x.ref !== ref)
    },
    async cerrar(ref, pin) {
      await sleep(600)
      checkPin(pin)
      find(ref)
      items = items.filter((x) => x.ref !== ref)
    },
    async opciones(sessionId) {
      await sleep(400)
      const repos = ['tienda', 'admin', 'docs', 'web', 'api'].map((r) => ({
        path: `/home/usuario/proyectos/acme/${r}`,
        proyecto: `mi-grupo/development/${r}`,
        nombre: r,
        rama: r === 'tienda' ? 'feature/DEMO-90' : 'main',
        ramas: r === 'tienda' ? ['feature/DEMO-90', 'feature/DEMO-88', 'local/experimento', 'develop', 'main'] : ['main'],
      }))
      repos.push({ path: '/home/usuario/proyectos/acme/extras/kit', proyecto: 'mi-grupo/development/innovacion/kit', nombre: 'kit', rama: 'feature/kit-mrs', ramas: ['feature/kit-mrs', 'main'] })
      return { repos, sugerido: sessionId ? { repo: '/home/usuario/proyectos/tienda-demo', rama: 'feature/DEMO-90' } : { repo: '', rama: '' }, equipo: EQUIPO }
    },
    async rama(_repo, rama) {
      await sleep(380)
      if (rama.startsWith('local/')) return { pusheada: false, target: 'develop', existente: null }
      if (rama === 'feature/DEMO-88') return { pusheada: true, target: 'develop', existente: { ref: '101:412', iid: 412, url: '' } }
      return { pusheada: true, target: rama.startsWith('feature/kit') ? 'main' : 'develop', existente: null }
    },
    async redactar(_repo, rama) {
      await sleep(2200)
      return {
        titulo: `feat: ${rama.split('/').pop()?.toLowerCase()} con validación de stock`,
        descripcion: 'Agrega la validación de stock antes de confirmar la reserva para evitar sobreventa.\n\n## Cambios\n- Nuevo servicio `StockGuard`.\n- Tests unitarios del caso borde con stock 0.\n\n## Cómo probar\n1. Reservar el último producto en dos pestañas.',
      }
    },
    async crear(body) {
      await sleep(900)
      const iid = 413 + items.length
      items = [mk({ pid: 101, iid, repo: body.repo.split('/').pop() || 'tienda', titulo: body.titulo, rama: body.rama, target: body.target, reviewers: body.reviewers.map(persona), pipeline: { estado: 'corriendo', id: 9_999, url: '' }, actualizado: hace(0) }), ...items]
      return { ref: `101:${iid}`, url: '' }
    },
  }
}
