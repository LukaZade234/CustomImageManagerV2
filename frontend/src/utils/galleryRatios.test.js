import { describe, expect, it } from 'vitest'
import {
  clampRatio,
  DEFAULT_RATIO,
  FILLERS,
  MAX_RATIO,
  MIN_RATIO,
  ratioFor,
  ratioOf,
} from './galleryRatios'

describe('clampRatio', () => {
  it('leaves an ordinary portrait alone', () => {
    expect(clampRatio(0.7)).toBe(0.7)
  })

  it('leaves an ordinary landscape alone', () => {
    expect(clampRatio(1.5)).toBe(1.5)
  })

  it('reins in a banner that would flatten its whole row', () => {
    expect(clampRatio(10)).toBe(MAX_RATIO)
  })

  it('reins in a strip that would make its row absurdly tall', () => {
    expect(clampRatio(0.05)).toBe(MIN_RATIO)
  })

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY, undefined, null, 'wide'])(
    'falls back to portrait for %s',
    (bad) => {
      expect(clampRatio(bad)).toBe(DEFAULT_RATIO)
    },
  )
})

describe('ratioOf', () => {
  it('measures a loaded image', () => {
    expect(ratioOf({ naturalWidth: 800, naturalHeight: 1200 })).toBeCloseTo(2 / 3)
  })

  it('returns null before an image has intrinsic size', () => {
    expect(ratioOf({ naturalWidth: 0, naturalHeight: 0 })).toBeNull()
    expect(ratioOf(null)).toBeNull()
    expect(ratioOf(undefined)).toBeNull()
  })

  it('clamps what it measures, so one odd image cannot wreck a row', () => {
    expect(ratioOf({ naturalWidth: 4000, naturalHeight: 200 })).toBe(MAX_RATIO)
  })
})

describe('fillers', () => {
  it('provides enough to absorb a last row', () => {
    expect(FILLERS.length).toBeGreaterThanOrEqual(4)
  })

  it('uses stable keys rather than array indices', () => {
    expect(new Set(FILLERS).size).toBe(FILLERS.length)
  })
})

describe('ratioFor', () => {
  it('prefers the dimensions the server already knows', () => {
    expect(ratioFor({ width: 900, height: 600 }, 0.5)).toBeCloseTo(1.5)
  })

  it('falls back to a measured ratio when the server has none', () => {
    expect(ratioFor({ width: null, height: null }, 1.2)).toBeCloseTo(1.2)
  })

  it('falls back to portrait when nothing is known yet', () => {
    expect(ratioFor({}, undefined)).toBe(DEFAULT_RATIO)
  })

  it('ignores nonsense dimensions rather than dividing by zero', () => {
    expect(ratioFor({ width: 100, height: 0 }, undefined)).toBe(DEFAULT_RATIO)
    expect(ratioFor({ width: 0, height: 100 }, undefined)).toBe(DEFAULT_RATIO)
  })

  it('clamps stored dimensions too, so one banner cannot flatten a row', () => {
    expect(ratioFor({ width: 4000, height: 200 }, undefined)).toBe(MAX_RATIO)
  })
})
