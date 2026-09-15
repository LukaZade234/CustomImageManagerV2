import { describe, expect, it } from 'vitest'

import { keysToTraits, poolLabel, traitsToKeys } from './characterTraits'

describe('traitsToKeys', () => {
  it('reads both genders and both roulette pools', () => {
    expect(traitsToKeys(true, true, 'Game & Animanga')).toEqual([
      'waifu',
      'husbando',
      'anime',
      'game',
    ])
  })

  it('reads a single pool label', () => {
    expect(traitsToKeys(false, true, 'Game')).toEqual(['husbando', 'game'])
    expect(traitsToKeys(true, false, 'Animanga')).toEqual(['waifu', 'anime'])
  })

  it('is empty for an ungendered, unpooled row', () => {
    expect(traitsToKeys(false, false, '')).toEqual([])
    expect(traitsToKeys(false, false, undefined)).toEqual([])
  })
})

describe('poolLabel', () => {
  it('names the combinations the backfill writes', () => {
    expect(poolLabel(['anime', 'game'])).toBe('Game & Animanga')
    expect(poolLabel(['game', 'anime'])).toBe('Game & Animanga')
    expect(poolLabel(['animanga'])).toBe('')
    expect(poolLabel(['anime'])).toBe('Animanga')
    expect(poolLabel(['game'])).toBe('Game')
    expect(poolLabel([])).toBe('')
  })
})

describe('keysToTraits', () => {
  it('round-trips a stored row through the editor', () => {
    const keys = traitsToKeys(true, true, 'Game & Animanga')
    expect(keysToTraits(keys)).toEqual({ is_female: true, is_male: true, pools: 'Game & Animanga' })
  })

  it('clears the traits when nothing is selected', () => {
    expect(keysToTraits([])).toEqual({ is_female: false, is_male: false, pools: '' })
  })
})
