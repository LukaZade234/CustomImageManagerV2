import { describe, expect, it } from 'vitest'
import {
  buildAiSegment,
  DISCORD_LIMIT_NITRO,
  DISCORD_LIMIT_REGULAR,
  splitAiCommandForLimit,
} from './aiCommandDiscord'

const url = (n) => `https://cdn.imgchest.com/files/abcdef${String(n).padStart(4, '0')}.png`

describe('buildAiSegment', () => {
  it('produces the Mudae form, prefixing every URL with $', () => {
    expect(buildAiSegment('Rem', ['a.png', 'b.png'])).toBe('$ai Rem $a.png $b.png')
  })

  it('does not double-prefix a URL that already starts with $', () => {
    expect(buildAiSegment('Rem', ['$a.png'])).toBe('$ai Rem $a.png')
  })
})

describe('splitAiCommandForLimit', () => {
  const urls = Array.from({ length: 40 }, (_, i) => url(i))

  it('keeps every part within the limit', () => {
    for (const limit of [DISCORD_LIMIT_REGULAR, DISCORD_LIMIT_NITRO]) {
      for (const part of splitAiCommandForLimit('Rem', urls, limit)) {
        expect(part.length).toBeLessThanOrEqual(limit)
      }
    }
  })

  it('starts every part with the command prefix, so each is pasteable alone', () => {
    for (const part of splitAiCommandForLimit('Rem', urls, DISCORD_LIMIT_REGULAR)) {
      expect(part.startsWith('$ai Rem ')).toBe(true)
    }
  })

  it('never loses a URL and never splits one in half', () => {
    const parts = splitAiCommandForLimit('Rem', urls, DISCORD_LIMIT_REGULAR)
    const joined = parts.join(' ')
    for (const u of urls) {
      // appears intact, and exactly once
      expect(joined.split(u).length - 1).toBe(1)
    }
  })

  it('holds those invariants across many limits', () => {
    for (let limit = 120; limit <= 2000; limit += 137) {
      const parts = splitAiCommandForLimit('Rem', urls, limit)
      const joined = parts.join(' ')
      for (const u of urls) {
        expect(joined.split(u).length - 1).toBe(1)
      }
      // Only a part carrying a single token may exceed the limit — a URL is
      // never cut, so one over-long URL is emitted whole by design.
      for (const part of parts) {
        if (part.length > limit) {
          expect(part.split(' $').length - 1).toBe(1)
        }
      }
    }
  })

  it('returns nothing for no URLs', () => {
    expect(splitAiCommandForLimit('Rem', [], DISCORD_LIMIT_REGULAR)).toEqual([])
  })

  it('emits an over-long single URL whole rather than truncating it', () => {
    const long = `https://cdn.imgchest.com/${'x'.repeat(300)}.png`
    const parts = splitAiCommandForLimit('Rem', [long], 100)
    expect(parts).toHaveLength(1)
    expect(parts[0]).toContain(long)
  })
})
