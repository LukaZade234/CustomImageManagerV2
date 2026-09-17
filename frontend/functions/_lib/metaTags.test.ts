/**
 * The link-preview metadata builder.
 *
 * The load-bearing rules: user-supplied names and series cannot break out of an
 * attribute, a character with no portrait omits og:image rather than emitting a
 * broken URL, and a shell with no </head> is returned untouched so the edge
 * function degrades to the existing generic card instead of serving nothing.
 */

import {
  buildMetaTags,
  type CharacterMeta,
  description,
  escapeAttr,
  injectIntoHead,
  portraitUrl,
} from './metaTags'

function character(overrides: Partial<CharacterMeta> = {}): CharacterMeta {
  return {
    name: 'Columbina',
    series: 'Genshin Impact',
    image: 'https://mudae.net/portrait.png',
    image_thumb: 'portraits/columbina.webp',
    custom_count: 12,
    in_library: true,
    ...overrides,
  }
}

describe('escapeAttr', () => {
  it('escapes the characters that can break out of an attribute', () => {
    expect(escapeAttr('a"b<c>d&e\'f')).toBe('a&quot;b&lt;c&gt;d&amp;e&#39;f')
  })

  it('escapes & first, so entities are not double-escaped', () => {
    // If & were replaced last it would turn the & of &lt; into &amp;lt;.
    expect(escapeAttr('<')).toBe('&lt;')
    expect(escapeAttr('&lt;')).toBe('&amp;lt;')
  })
})

describe('portraitUrl', () => {
  it('prefers the mirrored WebP on the image CDN', () => {
    expect(portraitUrl(character(), 'https://images.example')).toBe(
      'https://images.example/portraits/columbina.webp',
    )
  })

  it('falls back to the stored original when there is no mirror', () => {
    expect(portraitUrl(character({ image_thumb: '' }), 'https://images.example')).toBe(
      'https://mudae.net/portrait.png',
    )
  })

  it('uses the original when no image base is configured (dev)', () => {
    expect(portraitUrl(character(), '')).toBe('https://mudae.net/portrait.png')
  })

  it('returns empty when there is no image at all', () => {
    expect(portraitUrl(character({ image: '', image_thumb: '' }), '')).toBe('')
  })
})

describe('description', () => {
  it('carries the count and the series', () => {
    expect(description(character())).toBe('Genshin Impact · 12 custom images for Mudae')
  })

  it('singularises one image', () => {
    expect(description(character({ custom_count: 1 }))).toBe(
      'Genshin Impact · 1 custom image for Mudae',
    )
  })

  it('omits the separator when there is no series', () => {
    expect(description(character({ series: '', custom_count: 0 }))).toBe(
      '0 custom images for Mudae',
    )
  })
})

describe('buildMetaTags', () => {
  it('builds the full block with an absolute page URL', () => {
    const tags = buildMetaTags(character(), {
      pageUrl: 'https://example.com/character/Columbina',
      imageBase: 'https://images.example',
    })
    expect(tags).toContain('<meta property="og:title" content="Columbina — ImgManager">')
    expect(tags).toContain(
      '<meta property="og:description" content="Genshin Impact · 12 custom images for Mudae">',
    )
    expect(tags).toContain(
      '<meta property="og:url" content="https://example.com/character/Columbina">',
    )
    expect(tags).toContain('<meta name="twitter:card" content="summary_large_image">')
    expect(tags).toContain('content="https://images.example/portraits/columbina.webp"')
  })

  it('omits the image tags when there is no portrait', () => {
    const tags = buildMetaTags(character({ image: '', image_thumb: '' }), {
      pageUrl: 'https://example.com/character/X',
      imageBase: 'https://images.example',
    })
    expect(tags).not.toContain('og:image')
    expect(tags).not.toContain('twitter:image')
    expect(tags).toContain('og:title')
  })

  it('escapes a hostile name and series', () => {
    const tags = buildMetaTags(character({ name: '"><script>alert(1)</script>', series: 'a"b' }), {
      pageUrl: 'https://example.com/character/X',
      imageBase: '',
    })
    expect(tags).not.toContain('<script>')
    expect(tags).toContain('&lt;script&gt;')
    expect(tags).toContain('a&quot;b')
  })

  it('returns nothing for an unknown character', () => {
    expect(buildMetaTags(null, { pageUrl: 'https://x', imageBase: '' })).toBe('')
  })
})

describe('injectIntoHead', () => {
  it('splices the tags in before </head>', () => {
    const html = '<html><head><title>x</title></head><body></body></html>'
    const out = injectIntoHead(html, '<meta property="og:title" content="y">')
    expect(out).toContain('og:title')
    expect(out.indexOf('og:title')).toBeLessThan(out.indexOf('</head>'))
  })

  it('returns the document untouched when there is no </head>', () => {
    const html = '<html><body>not a shell</body></html>'
    expect(injectIntoHead(html, '<meta property="og:title" content="y">')).toBe(html)
  })

  it('returns the document untouched when there are no tags', () => {
    const html = '<html><head></head><body></body></html>'
    expect(injectIntoHead(html, '')).toBe(html)
  })
})
