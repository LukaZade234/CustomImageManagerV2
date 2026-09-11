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

describe('DESIGN.md invariants', () => {
  /**
   * DESIGN.md states these as rules, and for a while they were not true: nine
   * breakpoint values where it claimed four, nine radii where it claimed four,
   * a third shadow, and nine transitions on neither documented duration. A
   * design document whose rules are already false teaches the next person that
   * the rules are decorative, so they are enforced here rather than asserted
   * there.
   */
  const sheets = readdirSync(DIR)
    .filter((f) => f.endsWith('.css'))
    .map((f) => ({ file: f, css: readFileSync(join(DIR, f), 'utf8') }))
  const all = sheets.map((s) => s.css).join('\n')

  it('uses only the four documented breakpoints', () => {
    const widths = [...all.matchAll(/@media[^{]*\(\s*(?:max|min)-width:\s*(\d+)px/g)].map((m) =>
      Number(m[1]),
    )
    // 769 is the min-width complement of the 768 phone boundary.
    const allowed = new Set([480, 768, 769, 960, 1200])
    expect([...new Set(widths)].filter((w) => !allowed.has(w))).toEqual([])
  })

  it('expresses every border-radius as a token', () => {
    const values = [...all.matchAll(/border-radius:\s*([^;]+);/g)].map((m) => m[1].trim())
    // 50% is a circle, which is a shape rather than a step on the radius scale.
    const offScale = values.filter((v) => !v.startsWith('var(--') && v !== '50%')
    expect(offScale).toEqual([])
  })

  it('keeps the elevation vocabulary to two shadows, a scrim and a ring', () => {
    const values = [...all.matchAll(/box-shadow:\s*([^;]+);/g)].map((m) => m[1].trim())
    const allowed = new Set(['var(--shadow-sm)', 'var(--shadow-overlay)', 'var(--ring)', 'none'])
    expect([...new Set(values)].filter((v) => !allowed.has(v))).toEqual([])
  })

  it('runs every transition on the documented durations and curve', () => {
    const declarations = [...all.matchAll(/transition:\s*([^;]+);/g)].map((m) => m[1])
    const offScale = declarations.filter(
      (d) => /\d+(\.\d+)?s|\d+ms/.test(d) && !d.includes('var(--duration'),
    )
    expect(offScale).toEqual([])
  })
  it('sets every type size from the six-step scale', () => {
    // The exceptions are elements whose whole content is one drawn glyph — a
    // lightbox arrow, a dismiss cross, a disclosure caret, the check inside a
    // selection disc. `font-size` there is sizing a shape, not setting type,
    // which is the same exemption a circle has from the radius scale.
    const glyphs = /toast-dismiss|image-modal-close|image-modal-nav|::after/
    const offenders = []
    for (const { file, css } of sheets) {
      for (const { selector, body } of rules(css)) {
        for (const [, value] of body.matchAll(/font-size:\s*([^;]+);/g)) {
          const v = value.trim()
          if (v.startsWith('var(--type') || v === 'inherit') continue
          if (glyphs.test(selector)) continue
          offenders.push(`${file}  ${selector}  ${v}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})
