/// <reference types="vite/client" />
declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

declare module 'node:fs' {
  export function readFileSync(path: string, enc: 'utf8'): string
  export function writeFileSync(path: string, data: string): void
  export function readdirSync(path: string, o: { withFileTypes: true }): { name: string; isDirectory(): boolean }[]
  export function existsSync(path: string): boolean
}

declare module 'node:path' {
  export function join(...parts: string[]): string
  export function resolve(...parts: string[]): string
}

declare const __APP_BUILD__: string
