import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const manifest = JSON.parse(readFileSync('public/manifest.webmanifest', 'utf8'))

describe('manifest.webmanifest', () => {
  it('declara categorías y display_override solo standalone (sin cambiar la apariencia)', () => {
    expect(manifest.categories).toEqual(['productivity', 'developer'])
    expect(manifest.display_override).toEqual(['standalone'])
    expect(manifest.display).toBe('standalone')
  })
  it('el manifest base no trae shortcuts: los suman las piezas al compilar', () => {
    expect(manifest).not.toHaveProperty('shortcuts')
  })
})
