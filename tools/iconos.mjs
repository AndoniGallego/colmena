#!/usr/bin/env node
// Regenera favicon e íconos PWA desde la variante de logo de Colmena.
//   node tools/iconos.mjs [panal|abeja|monograma]
// Rasteriza con Chromium de Playwright (busca playwright-core en el frontend, en PLAYWRIGHT_CORE
// o en la caché de npx) y arma favicon.ico con ImageMagick. Requiere Node >= 22.18 (importa TS).
import { execFileSync } from 'node:child_process'
import { existsSync, readdirSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { createRequire } from 'node:module'
import { homedir, tmpdir } from 'node:os'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { DEFAULT_LOGO, LOGO_VARIANTS, iconSvg } from '../frontend/src/lib/colmena.ts'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const pub = join(root, 'frontend', 'public')
const variant = process.argv[2] ?? DEFAULT_LOGO
if (!LOGO_VARIANTS.includes(variant)) {
  console.error(`Variante desconocida: ${variant}. Opciones: ${LOGO_VARIANTS.join(', ')}`)
  process.exit(1)
}

function findPlaywright() {
  const own = process.env.PLAYWRIGHT_CORE
  if (own) return createRequire(import.meta.url)(own)
  const bases = [join(root, 'frontend', 'package.json')]
  const npx = join(homedir(), '.npm', '_npx')
  if (existsSync(npx)) for (const d of readdirSync(npx)) bases.push(join(npx, d, 'package.json'))
  for (const b of bases) {
    try {
      return createRequire(b)('playwright-core')
    } catch {
      /* siguiente */
    }
  }
  throw new Error('No encontré playwright-core. Definí PLAYWRIGHT_CORE con la ruta al paquete.')
}

// [archivo, px, opciones]
const targets = [
  ['icons/icon-512.png', 512, {}],
  ['icons/icon-192.png', 192, {}],
  ['icons/apple-touch-icon.png', 180, { radius: 0 }],
  ['icons/icon-maskable-512.png', 512, { radius: 0, scale: 5.2 }],
  ['favicon-32.png', 32, { radius: 120 }],
]
const svgs = [
  ['icons/icon.svg', iconSvg(variant)],
  ['icons/icon-maskable.svg', iconSvg(variant, { radius: 0, scale: 5.2 })],
  ['favicon.svg', iconSvg(variant, { px: 32, radius: 120 })],
]

const { chromium } = findPlaywright()
const browser = await chromium.launch()
const page = await browser.newPage({ deviceScaleFactor: 1 })
async function raster(svg, px, file) {
  await page.setViewportSize({ width: px, height: px })
  await page.setContent(`<html><body style="margin:0;background:transparent">${svg}</body></html>`)
  await page.locator('svg').screenshot({ path: file, omitBackground: true })
}

for (const [file, px, o] of targets) await raster(iconSvg(variant, { px, ...o }), px, join(pub, file))
const tmp = mkdtempSync(join(tmpdir(), 'colmena-ico-'))
await raster(iconSvg(variant, { px: 16, radius: 120 }), 16, join(tmp, '16.png'))
await raster(iconSvg(variant, { px: 32, radius: 120 }), 32, join(tmp, '32.png'))
await browser.close()

for (const [file, svg] of svgs) writeFileSync(join(pub, file), svg.replace(/ width="\d+" height="\d+"/, ''))
execFileSync('convert', [join(tmp, '16.png'), join(tmp, '32.png'), join(pub, 'favicon.ico')])
rmSync(tmp, { recursive: true, force: true })
console.log(`Íconos regenerados con la variante "${variant}".`)
