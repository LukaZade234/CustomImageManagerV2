import { describe, expect, it } from 'vitest'
import { themeFromSeed } from './accentFromImage'

const toRgb = (hex) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
const toLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const luminance = (hex) => {
  const [r, g, b] = toRgb(hex).map(toLinear)
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}
const contrast = (hexA, hexB) => {
  const a = luminance(hexA)
  const b = luminance(hexB)
  return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05)
}
/** Hue in degrees, for asserting the family rather than an exact value. */
function hueOf(hexColour) {
  const [r, g, b] = toRgb(hexColour)
  const max = Math.max(r, g, b)
  const d = max - Math.min(r, g, b)
  if (d < 1e-9) return null
  let h
  if (max === r) h = (((g - b) / d) % 6) * 60
  else if (max === g) h = ((b - r) / d + 2) * 60
  else h = ((r - g) / d + 4) * 60
  return (h + 360) % 360
}
const hueGap = (a, b) => {
  const d = Math.abs(a - b) % 360
  return d > 180 ? 360 - d : d
}

describe('themeFromSeed', () => {
  it('keeps the seed’s hue family', () => {
    const theme = themeFromSeed('#1cb0b6') // teal
    expect(theme).not.toBeNull()
    expect(hueGap(hueOf(theme.light.accent), 183)).toBeLessThan(20)
    expect(hueGap(theme.hue, 183)).toBeLessThan(20)
  })

  it('keeps a pale seed pale in dark mode and legible in light mode', () => {
    // Lucy's measured seed: a blue-white. Dark mode may stay near it; light
    // mode must walk down to clear 4.5:1 against white, which is what turns a
    // bluey-white into a soft dusty blue rather than refusing it.
    const theme = themeFromSeed('#aeb7d2')
    expect(theme).not.toBeNull()
    const dark = toRgb(theme.dark.accent)
    expect(Math.min(...dark)).toBeGreaterThan(0.55)
    expect(contrast(theme.light.accent, '#ffffff')).toBeGreaterThanOrEqual(4.5)
  })

  it('declines a seed too grey to theme a page with', () => {
    expect(themeFromSeed('#808080')).toBeNull()
    expect(themeFromSeed('#14171d')).toBeNull()
  })

  it('declines absent and malformed seeds', () => {
    expect(themeFromSeed(null)).toBeNull()
    expect(themeFromSeed('')).toBeNull()
    expect(themeFromSeed('not-a-colour')).toBeNull()
    expect(themeFromSeed('#12345')).toBeNull()
  })

  describe('derived theme', () => {
    // Saturated, pale, warm and cool seeds alike: the contrast floors are a
    // property of the derivation, not of any particular seed.
    const seeds = ['#1cb0b6', '#d23c46', '#78c850', '#f0dc3c', '#b45adc', '#aeb7d2', '#602c29']

    it('meets the contrast floor for accent against its page ground', () => {
      for (const seed of seeds) {
        const theme = themeFromSeed(seed)
        expect(theme).not.toBeNull()
        expect(contrast(theme.light.accent, '#ffffff')).toBeGreaterThanOrEqual(4.5)
        expect(contrast(theme.dark.accent, '#14171d')).toBeGreaterThanOrEqual(4.5)
      }
    })

    it('keeps fg legible against its own accent, in both themes', () => {
      for (const seed of seeds) {
        const theme = themeFromSeed(seed)
        expect(theme).not.toBeNull()
        expect(contrast(theme.light.fg, theme.light.accent)).toBeGreaterThanOrEqual(4.5)
        expect(contrast(theme.dark.fg, theme.dark.accent)).toBeGreaterThanOrEqual(4.5)
      }
    })

    it('keeps subtle legible when the accent sits on it as text', () => {
      for (const seed of seeds) {
        const theme = themeFromSeed(seed)
        expect(theme).not.toBeNull()
        expect(contrast(theme.light.accent, theme.light.subtle)).toBeGreaterThanOrEqual(4.5)
        expect(contrast(theme.dark.accent, theme.dark.subtle)).toBeGreaterThanOrEqual(4.5)
      }
    })

    it('derives hover as a neighbour of the accent, not a different colour', () => {
      for (const seed of seeds) {
        const theme = themeFromSeed(seed)
        expect(hueGap(hueOf(theme.light.hover), hueOf(theme.light.accent))).toBeLessThan(15)
        expect(hueGap(hueOf(theme.dark.hover), hueOf(theme.dark.accent))).toBeLessThan(15)
      }
    })
  })
})
