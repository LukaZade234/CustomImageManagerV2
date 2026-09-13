/**
 * The document must not send a Referer.
 *
 * Portraits are hotlinked from mudae.net, which answers 403 when the request
 * carries a foreign Referer and 200 when it carries none. Without the opt-out
 * every main image 403s in the browser while curl looks fine -- exactly the
 * failure this pins.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const html = readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', 'index.html'), 'utf8')

describe('index.html', () => {
  it('opts out of sending a Referer', () => {
    expect(html).toMatch(/<meta\s+name="referrer"\s+content="no-referrer"\s*\/?>/i)
  })
})
