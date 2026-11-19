import type { AtRule, Plugin, Rule } from 'postcss'

const QUERY = '(hover: hover) and (pointer: fine)'

const tieneHover = (sel: string) => /:hover/.test(sel.replace(/:not\((?:[^()]|\([^()]*\))*\)/g, ''))

function dentroDeHover(rule: Rule) {
  for (let p = rule.parent; p && p.type !== 'root'; p = p.parent) {
    if (p.type !== 'atrule') continue
    const at = p as AtRule
    if (at.name === 'keyframes' || at.name.endsWith('-keyframes')) return true
    if (at.name === 'media' && /hover:\s*hover/.test(at.params)) return true
  }
  return false
}

export default function hoverSoloMouse(): Plugin {
  return {
    postcssPlugin: 'hover-solo-mouse',
    Rule(rule, { AtRule }) {
      if (!rule.selectors.some(tieneHover) || dentroDeHover(rule)) return
      const sinHover = rule.selectors.filter((s) => !tieneHover(s))
      const conHover = rule.selectors.filter(tieneHover)
      const envuelto = rule.clone({ selectors: conHover })
      const media = new AtRule({ name: 'media', params: QUERY, source: rule.source })
      media.append(envuelto)
      rule.after(media)
      if (sinHover.length) rule.selectors = sinHover
      else rule.remove()
    },
  }
}
hoverSoloMouse.postcss = true
