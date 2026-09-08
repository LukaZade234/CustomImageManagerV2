import { describe, expect, it } from 'vitest'
import { sanitizeFilenameFromUrl, uniqueFilenames } from './downloadCustomImages'

describe('sanitizeFilenameFromUrl', () => {
  it('takes the last path segment', () => {
    expect(sanitizeFilenameFromUrl('https://cdn.imgchest.com/files/abc.png')).toBe('abc.png')
  })

  it('replaces characters that are unsafe in a filename', () => {
    expect(sanitizeFilenameFromUrl('https://x/a b?c=1.png')).toBe('a_b_c_1.png')
  })

  it('falls back for empty input', () => {
    expect(sanitizeFilenameFromUrl('')).toBe('image.png')
  })
})

describe('uniqueFilenames', () => {
  it('passes distinct names through unchanged', () => {
    expect(uniqueFilenames(['x/a.png', 'x/b.png'])).toEqual(['a.png', 'b.png'])
  })

  it('disambiguates duplicates while keeping the extension', () => {
    expect(uniqueFilenames(['x/a.png', 'y/a.png', 'z/a.png'])).toEqual([
      'a.png',
      'a_2.png',
      'a_3.png',
    ])
  })

  it('handles names with no extension', () => {
    expect(uniqueFilenames(['x/a', 'y/a'])).toEqual(['a', 'a_2'])
  })

  it('always returns one name per URL, all unique', () => {
    const urls = Array.from({ length: 25 }, (_, i) => `https://cdn/${i % 4}/dup.png`)
    const names = uniqueFilenames(urls)
    expect(names).toHaveLength(urls.length)
    expect(new Set(names).size).toBe(urls.length)
  })
})
