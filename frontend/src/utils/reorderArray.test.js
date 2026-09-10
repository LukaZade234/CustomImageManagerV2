/**
 * The ordering rules behind drag-to-reorder.
 *
 * These were previously buried in a 1,600-line component alongside pointer
 * handling, which made them effectively untestable — and they are the part a
 * user actually notices, since the gallery order is the order $ai emits.
 */
import { describe, expect, it } from 'vitest'
import { adjustDropTarget, moveGroupInArray, ordersEqual } from './reorderArray'

const abcde = ['a', 'b', 'c', 'd', 'e']

describe('moveGroupInArray', () => {
  // The rule: the selection lands immediately *before* whatever was at the drop
  // index. Dropping 'a' onto 'c' puts 'a' in front of 'c'.
  it('moves one image forwards, landing before the drop target', () => {
    expect(moveGroupInArray(abcde, [0], 2)).toEqual(['b', 'a', 'c', 'd', 'e'])
  })

  it('moves one image backwards', () => {
    expect(moveGroupInArray(abcde, [3], 1)).toEqual(['a', 'd', 'b', 'c', 'e'])
  })

  it('keeps a multi-image selection in its own order', () => {
    expect(moveGroupInArray(abcde, [0, 1], 3)).toEqual(['c', 'a', 'b', 'd', 'e'])
  })

  it('handles a selection given out of order', () => {
    expect(moveGroupInArray(abcde, [3, 1], 0)).toEqual(['b', 'd', 'a', 'c', 'e'])
  })

  it('gathers a non-contiguous selection into one run', () => {
    expect(moveGroupInArray(abcde, [0, 4], 2)).toEqual(['b', 'a', 'e', 'c', 'd'])
  })

  it('never loses or duplicates an image', () => {
    for (const from of [[0], [1, 2], [0, 4], [2, 3, 4]]) {
      for (let to = 0; to < abcde.length; to++) {
        const out = moveGroupInArray(abcde, from, to)
        expect([...out].sort()).toEqual([...abcde].sort())
        expect(out).toHaveLength(abcde.length)
      }
    }
  })

  it('is a no-op when dropping a selection onto itself', () => {
    expect(moveGroupInArray(abcde, [1], 1)).toEqual(abcde)
  })

  it('copes with an out-of-range target', () => {
    expect(moveGroupInArray(abcde, [0], 99)).toHaveLength(5)
    expect(moveGroupInArray(abcde, [0], -5)).toHaveLength(5)
  })

  it('handles an empty array', () => {
    expect(moveGroupInArray([], [], 0)).toEqual([])
  })
})

describe('adjustDropTarget', () => {
  it('leaves a target outside the selection alone', () => {
    expect(adjustDropTarget(3, new Set([0, 1]), 5)).toBe(3)
  })

  it('skips forwards past the selection', () => {
    expect(adjustDropTarget(1, new Set([1, 2]), 5)).toBe(3)
  })

  it('falls back to searching backwards at the end', () => {
    expect(adjustDropTarget(4, new Set([3, 4]), 5)).toBe(2)
  })

  it('clamps a target beyond the array', () => {
    expect(adjustDropTarget(99, new Set(), 5)).toBe(4)
    expect(adjustDropTarget(-3, new Set(), 5)).toBe(0)
  })

  it('returns 0 for an empty gallery rather than a negative index', () => {
    expect(adjustDropTarget(2, new Set(), 0)).toBe(0)
  })
})

describe('ordersEqual', () => {
  it('is true for the same order', () => {
    expect(ordersEqual(['a', 'b'], ['a', 'b'])).toBe(true)
  })

  it('is false for a different order', () => {
    expect(ordersEqual(['a', 'b'], ['b', 'a'])).toBe(false)
  })

  it('is false for different lengths', () => {
    expect(ordersEqual(['a'], ['a', 'b'])).toBe(false)
  })
})
