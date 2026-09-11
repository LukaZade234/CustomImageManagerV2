/**
 * Foreground tokens must not be used on the wrong background.
 *
 * The palette has two kinds of surface for each status colour: the solid fill
 * (`--accent`) and a pale tint (`--accent-subtle`). Each has its own correct
 * foreground — `--accent-fg` is designed to sit on the *solid* fill, and
 * `--accent` itself is what reads on the tint.
 *
 * Pairing `--accent-fg` with `--accent-subtle` puts white on near-white. That
 * shipped on the profile's theme control: the selected option was unreadable in
 * light mode and, less visibly, in dark mode too. Nothing caught it because the
 * page still rendered and every test still passed — the text was simply the
 * same colour as what it sat on.
 */
import { readdirSync, readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const DIR = dirname(fileURLToPath(import.meta.url))

function rules(css) {
  // Good enough for flat rule blocks, which is all these stylesheets contain.
  return [...css.matchAll(/([^{}]+)\{([^{}]*)\}/g)].map((m) => ({
    selector: m[1].trim().split('\n').pop().trim(),
    body: m[2],
  }))
}

const sheets = readdirSync(DIR)
  .filter((f) => f.endsWith('.css'))
  .map((f) => ({ file: f, css: readFileSync(join(DIR, f), 'utf8') }))

describe('colour token pairings', () => {
  it('has stylesheets to check', () => {
    expect(sheets.length).toBeGreaterThan(3)
  })

  it.each(['accent', 'success', 'danger'])(
    'never puts --%s-fg on the matching --*-subtle tint',
    (name) => {
      const offenders = []
      for (const { file, css } of sheets) {
        for (const { selector, body } of rules(css)) {
          const onTint = new RegExp(`background(-color)?\\s*:\\s*var\\(--${name}-subtle\\)`)
          const wrongFg = new RegExp(`(^|[^-])color\\s*:\\s*var\\(--${name}-fg\\)`, 'm')
          if (onTint.test(body) && wrongFg.test(body)) {
            offenders.push(`${file}  ${selector}`)
          }
        }
      }
      expect(offenders, `--${name}-fg belongs on the solid --${name} fill`).toEqual([])
    },
  )
})

describe('justified card rows', () => {
  /**
   * `.profile-card` must opt out of the global border-box.
   *
   * The grid justifies a row by giving every card a flex-basis and a flex-grow
   * proportional to its image's aspect ratio, so the row grows by one constant
   * and every image lands at the same height. That only holds while the basis
   * describes the *image*. Under border-box the card's padding and border sit
   * inside the basis, so each card subtracts the same chrome and then divides by
   * its own ratio — leaving a wide card ~26px shorter than a narrow one beside
   * it, which reads as the images having inconsistent margins.
   *
   * It is one easily-missed declaration, so it is pinned here.
   */
  const css = readFileSync(join(DIR, 'pages.css'), 'utf8')

  it('keeps the card on content-box so the basis is the image width', () => {
    const card = rules(css).find((r) => r.selector === '.profile-card')
    expect(card, '.profile-card rule not found').toBeTruthy()
    expect(card.body).toMatch(/box-sizing:\s*content-box/)
  })

  it('gives the image box the card ratio, so there is nothing to letterbox into', () => {
    const image = rules(css).find((r) => r.selector === '.profile-card__image')
    expect(image.body).toMatch(/aspect-ratio:\s*var\(--ratio/)
  })
})
