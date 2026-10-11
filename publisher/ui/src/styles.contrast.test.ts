import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

/** docs/PI_UI_REDESIGN_PLAN.md §9: every badge tone (and the accent button) reads at ≥ 4.5:1 in light and dark. */
const css = readFileSync(resolve(import.meta.dirname, 'styles.css'), 'utf8')

function tokens(block: string): Record<string, string> {
  return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})\s*;/gi)].map((m) => [m[1] as string, (m[2] as string).toLowerCase()]))
}

const light = tokens(css.slice(css.indexOf(':root {'), css.indexOf('}', css.indexOf(':root {'))))
const darkStart = css.indexOf('@media (prefers-color-scheme: dark)')
const dark = { ...light, ...tokens(css.slice(darkStart, css.indexOf('}', css.indexOf(':root {', darkStart)))) }

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
  }) as [number, number, number]
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x) as [number, number]
  return (hi + 0.05) / (lo + 0.05)
}

const PAIRS: [string, string, string][] = [
  ['good', 'good', 'good-bg'],
  ['bad', 'bad', 'bad-bg'],
  ['warn', 'warn', 'warn-bg'],
  ['info', 'info', 'info-bg'],
  ['neutral', 'muted', 'neutral-bg'],
  ['accent button', 'accent-text', 'accent'],
  ['muted text', 'muted', 'surface'],
]

describe('colour contrast', () => {
  it('found the light and dark tokens', () => {
    expect(Object.keys(light).length).toBeGreaterThan(15)
    expect(dark.surface).not.toBe(light.surface)
  })

  for (const [scheme, t] of [['light', light], ['dark', dark]] as const) {
    for (const [name, fg, bg] of PAIRS) {
      it(`${scheme}: ${name} is at least 4.5:1`, () => {
        const ratio = contrast(t[fg] ?? '', t[bg] ?? '')
        expect(ratio, `${fg} ${t[fg]} on ${bg} ${t[bg]}`).toBeGreaterThanOrEqual(4.5)
      })
    }
  }
})
