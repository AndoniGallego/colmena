/// <reference types="vitest/config" />
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import hoverSoloMouse from './postcss/hoverSoloMouse'
import { fusionarManifest, leerManifestPieza, type ManifestPieza } from './src/lib/manifestPiezas'
import { baseDeBuild, rebasarManifest } from './src/lib/modoDemo'

declare const process: { env: Record<string, string | undefined> }

const BUILD = Date.now().toString(36)

const swVersion = () => {
  let outDir = 'dist'
  return {
    name: 'sw-version',
    apply: 'build' as const,
    configResolved(c: { root: string; build: { outDir: string } }) {
      outDir = resolve(c.root, c.build.outDir)
    },
    closeBundle() {
      const f = join(outDir, 'sw.js')
      writeFileSync(f, readFileSync(f, 'utf8').replace('__BUILD_ID__', BUILD))
    },
  }
}

/** Suma al manifest del build los shortcuts de las piezas montadas (src/piezas/<pieza>/manifest.json). */
const piezasManifest = () => {
  let outDir = 'dist'
  let root = '.'
  let base = '/'
  return {
    name: 'piezas-manifest',
    apply: 'build' as const,
    configResolved(c: { root: string; base: string; build: { outDir: string } }) {
      root = c.root
      base = c.base
      outDir = resolve(c.root, c.build.outDir)
    },
    closeBundle() {
      const dir = join(root, 'src/piezas')
      const extras: ManifestPieza[] = readdirSync(dir, { withFileTypes: true })
        .filter((d) => d.isDirectory() && existsSync(join(dir, d.name, 'manifest.json')))
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((d) => leerManifestPieza(d.name, readFileSync(join(dir, d.name, 'manifest.json'), 'utf8')))
      const f = join(outDir, 'manifest.webmanifest')
      writeFileSync(f, JSON.stringify(rebasarManifest(fusionarManifest(JSON.parse(readFileSync(f, 'utf8')), extras), base), null, 2) + '\n')
    },
  }
}

export default defineConfig(({ command }) => ({
  base: baseDeBuild(process.env),
  define: { __APP_BUILD__: JSON.stringify(command === 'build' ? BUILD : 'dev') },
  plugins: [vue(), swVersion(), piezasManifest()],
  css: { postcss: { plugins: [hoverSoloMouse()] } },
  server: {
    host: '127.0.0.1',
    port: 5173,
    fs: { allow: ['..'] },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8770',
        changeOrigin: false,
        // El backend exige Origin igual al Host: en dev el navegador manda el del 5173.
        configure: (proxy: any) =>
          proxy.on('proxyReq', (req: any) => req.getHeader('origin') && req.setHeader('origin', 'http://127.0.0.1:8770')),
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
    target: 'es2022',
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return
          if (id.includes('@xterm/')) return 'xterm'
          if (
            id.includes('markdown-it')
            || id.includes('linkify-it')
            || id.includes('mdurl')
            || id.includes('uc.micro')
            || id.includes('punycode')
            || id.includes('/entities/')
            || id.includes('dompurify')
          ) return 'markdown'
          if (id.includes('/gsap')) return 'gsap'
          if (id.includes('/vue/') || id.includes('@vue/')) return 'vue'
        },
      },
    },
  },
  // Sin caché de módulos en disco: el registro de piezas sale de un glob y la caché lo dejaba viejo al sumar o sacar una pieza.
  test: { environment: 'node', include: ['src/**/*.test.ts', 'postcss/**/*.test.ts'], fsModuleCache: false },
}))
