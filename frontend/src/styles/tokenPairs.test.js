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

describe('text contrast (WCAG AA)', () => {
  /**
   * `--text-subtle` sat a full ramp step too faint: #7c8595 is 3.72:1 on white
   * and 4.49:1 on the dark card, so 13px hints, placeholders and notes failed
   * AA in both themes. It is now tuned per theme (4.5:1 on both --bg and
   * --surface), and this pins it — a decorative-looking token is exactly the
   * kind that silently drifts back.
   */
  const css = readFileSync(join(DIR, 'tokens.css'), 'utf8')

  function block(selector) {
    const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const m = css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\}`))
    if (!m) throw new Error(`token block not found: ${selector}`)
    return m[1]
  }
  const base = block(':root')
  const dark = block(':root[data-theme="dark"]')
  const ramp = Object.fromEntries(
    [...base.matchAll(/(--n-\d+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]),
  )
  const resolve = (value, tokens) => {
    const m = value.trim().match(/^var\((--[\w-]+)\)$/)
    return m ? (tokens[m[1]] ?? value) : value.trim()
  }
  const decl = (body, name) => {
    const m = body.match(new RegExp(`--${name}:\\s*([^;]+);`))
    return m ? m[1].trim() : null
  }
  const luminance = (hex) => {
    const [r, g, b] = [1, 3, 5].map((i) => Number.parseInt(hex.slice(i, i + 2), 16) / 255)
    const f = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)
  }
  const contrast = (a, b) => {
    const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x)
    return (hi + 0.05) / (lo + 0.05)
  }

  it.each([
    ['light', base],
    ['dark', dark],
  ])('keeps muted and subtle text at 4.5:1 in %s mode', (_mode, tokens) => {
    const bg = resolve(decl(tokens, 'bg'), ramp)
    const surface = resolve(decl(tokens, 'surface'), ramp)
    for (const name of ['text-muted', 'text-subtle']) {
      const fg = resolve(decl(tokens, name), ramp)
      for (const behind of [bg, surface]) {
        expect(contrast(fg, behind), `${name} on ${behind}`).toBeGreaterThanOrEqual(4.5)
      }
    }
  })
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
  it('spaces everything on the documented 4px scale', () => {
    // The last of DESIGN.md's claims with nothing behind it. Radii, breakpoints,
    // shadows and type sizes each got a test; spacing said "no value outside the
    // scale appears in the system" while 48 declarations sat off it.
    //
    // The exceptions are the values that are not steps at all: hairlines and the
    // 1-2px optical nudges that sit under a border, and the two clearances the
    // fixed action bar reserves, which are measurements of a control's height.
    const SCALE = new Set([0, 4, 8, 12, 16, 20, 24, 32, 40, 48, 64])
    const OPTICAL = new Set([1, 2])
    const MEASURED = new Set([96, 140])
    const offScale = []
    for (const { file, css } of sheets) {
      for (const [, prop, value] of css.matchAll(
        /((?:margin|padding|gap|row-gap|column-gap)[a-z-]*)\s*:\s*([^;]+);/g,
      )) {
        for (const token of value.split(/\s+/)) {
          const match = /^(-?\d+(?:\.\d+)?)(px|rem)$/.exec(token)
          if (!match) continue
          const px = Math.abs(Number(match[1]) * (match[2] === 'rem' ? 16 : 1))
          if (SCALE.has(px) || OPTICAL.has(px) || MEASURED.has(px)) continue
          offScale.push(`${file}  ${prop}: ${token}`)
        }
      }
    }
    expect(offScale).toEqual([])
  })
  it('orders the dialog layers so a dialog opened over the lightbox wins', () => {
    // The report dialog opens over the image lightbox. The lightbox once sat on
    // a hand-picked z-index of 2000, far above --z-modal (300), so the report
    // dialog painted underneath the scrim that captured its clicks. The layer
    // order is the actual fix; this pins it.
    const tokens = readFileSync(join(DIR, 'tokens.css'), 'utf8')
    const layers = Object.fromEntries(
      [...tokens.matchAll(/--z-([a-z]+):\s*(\d+);/g)].map((m) => [m[1], Number(m[2])]),
    )
    expect(layers.lightbox).toBeLessThan(layers.modal)
    expect(layers.modal).toBeLessThan(layers.toast)

    const imageModal = rules(readFileSync(join(DIR, 'components.css'), 'utf8')).find(
      (r) => r.selector === '.image-modal',
    )
    expect(imageModal.body).toMatch(/z-index:\s*var\(--z-lightbox\)/)
  })

  it('lets the grid row own the space around the header band buttons', () => {
    // Save sits in column one and Edit/$ai in column two of the same grid row,
    // so they are level by construction. A vertical margin or padding on either
    // cell breaks that quietly — it moves one half of the row and nothing else,
    // which is exactly the bug the grid replaced. The row gap owns this space.
    const cells = ['.save-button', '.char-page-actions']
    const vertical = /^(margin|padding)(-top|-bottom)?$/
    const offenders = []
    for (const { file, css } of sheets) {
      for (const { selector, body } of rules(css)) {
        if (!cells.some((cell) => selector.endsWith(cell))) continue
        for (const [, prop, value] of body.matchAll(/([a-z-]+)\s*:\s*([^;]+);/g)) {
          if (!vertical.test(prop)) continue
          if (/^0( |$)/.test(value.trim())) continue
          offenders.push(`${file}  ${selector}  ${prop}: ${value.trim()}`)
        }
      }
    }
    expect(offenders).toEqual([])
  })
})

describe('the folded nav keeps its icons', () => {
  /**
   * On a narrow bar the nav buttons shed their word and become icon-only, via a
   * blanket `.btn-nav span { display: none }`. The notification bell puts its
   * `<svg>` inside a span (so the pulse ring can be a circle around just the
   * icon), which that rule then hid — the button stayed but rendered as an empty
   * square: clickable, spaced, and invisible, with the pulse on a hidden element.
   * A span is not a label just because it is a span, so the hide must exempt it.
   */
  it('does not hide the notification bell wrapper with the word-labels', () => {
    const hiders = rules(readFileSync(join(DIR, 'components.css'), 'utf8')).filter(
      ({ selector, body }) =>
        selector.includes('.btn-nav') && selector.includes('span') && /display:\s*none/.test(body),
    )
    expect(hiders.length, 'expected a rule that folds nav labels').toBeGreaterThan(0)
    for (const { selector } of hiders) {
      expect(selector, `"${selector}" would hide the bell icon and its pulse`).toContain(
        '.navbar-notifications__bell',
      )
    }
  })
})
