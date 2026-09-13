/**
 * A character's accent seed, turned into the full, usable UI theme.
 *
 * The seed itself — the one colour a character is "about" — is measured
 * server-side from the portrait and the pooled gallery, where it is computed
 * once per gallery change rather than once per browser visit
 * (accent_extract.py). What happens here is purely a display concern: a colour
 * taken from artwork has no obligation to be legible against a white card, and
 * most are not, so each of the four roles the design system needs is fitted to
 * a contrast floor in OKLCH, in both colour schemes.
 *
 * The derivation mirrors the design tokens' own relationships (measured
 * directly off tokens.css): hover is the accent shifted about 0.07 of OKLCH
 * lightness toward the page's far end and very slightly desaturated; subtle is
 * pushed close to that end entirely, at low chroma; fg is white in light mode
 * (guaranteed legible, because the accent was itself fit for contrast against
 * white) and a dark, hue-tinted near-black in dark mode, fit the same way
 * against the accent it sits on rather than against the page.
 */

const clamp = (n, lo, hi) => Math.min(hi, Math.max(lo, n))

/* ---- colour space ------------------------------------------------------- */

const srgbToLinear = (c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4)
const linearToSrgb = (c) =>
  c <= 0.0031308 ? c * 12.92 : 1.055 * Math.max(c, 0) ** (1 / 2.4) - 0.055

function rgbToOklch(r, g, b) {
  const lr = srgbToLinear(r)
  const lg = srgbToLinear(g)
  const lb = srgbToLinear(b)
  const l = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb)
  const m = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb)
  const s = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb)
  const L = 0.2104542553 * l + 0.793617785 * m - 0.0040720468 * s
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s
  return { L, C: Math.hypot(A, B), h: (Math.atan2(B, A) * 180) / Math.PI }
}

function oklabToRgb(L, A, B) {
  const l = (L + 0.3963377774 * A + 0.2158037573 * B) ** 3
  const m = (L - 0.1055613458 * A - 0.0638541728 * B) ** 3
  const s = (L - 0.0894841775 * A - 1.291485548 * B) ** 3
  return [
    clamp(linearToSrgb(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s), 0, 1),
    clamp(linearToSrgb(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s), 0, 1),
    clamp(linearToSrgb(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s), 0, 1),
  ]
}

function oklchToRgb(L, C, hDeg) {
  const h = (hDeg * Math.PI) / 180
  return oklabToRgb(L, C * Math.cos(h), C * Math.sin(h))
}

const hex = (rgb) =>
  `#${rgb
    .map((v) =>
      Math.round(v * 255)
        .toString(16)
        .padStart(2, '0'),
    )
    .join('')}`

const luminance = ([r, g, b]) =>
  0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b)

function contrast(a, b) {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

/**
 * Walk lightness in OKLCH until the colour clears `target` against `bg`.
 * Hue and chroma are held, so the result is still recognisably the same colour
 * — which is the whole point of doing this in OKLCH rather than by mixing
 * toward black or white. `bg` can be a page ground or another swatch (fg
 * against its own accent, subtle against the accent it sits beside) — the
 * maths does not care which.
 */
function fitContrast(L, C, h, bg, target, lighten) {
  // A small margin over the target: the walk is continuous but the result is
  // quantised to 8-bit hex immediately after, which can round the achieved
  // contrast back under an exact target by a few thousandths.
  const goal = target + 0.03
  for (let i = 0; i < 140; i++) {
    const LL = L + (lighten ? 0.01 * i : -0.01 * i)
    if (LL < 0.02 || LL > 0.99) break
    const rgb = oklchToRgb(LL, C, h)
    if (contrast(rgb, bg) >= goal) return rgb
  }
  return oklchToRgb(lighten ? 0.99 : 0.02, C, h)
}

/**
 * Walk from `from` toward `toward` in OKLab — not OKLCH lightness with chroma
 * held — so a "near white" or "near black" result actually converges on the
 * literal endpoint rather than stalling a few percent short of it. Lightness
 * *and* chroma shrink together as the mix approaches 1, which is exactly what
 * a tint fading toward true white or true black does and an L-only shift does
 * not: a saturated colour walked to L=0.99 at fixed chroma is still visibly
 * tinted and short of white's own contrast ceiling, which is the gap that
 * left --accent-subtle failing its own legibility check for a few hues.
 */
function fitMixToward(fromRgb, towardRgb, bg, target) {
  const a = rgbToOklch(...fromRgb)
  const fromLab = [
    a.L,
    a.C * Math.cos((a.h * Math.PI) / 180),
    a.C * Math.sin((a.h * Math.PI) / 180),
  ]
  const b = rgbToOklch(...towardRgb)
  const towardLab = [
    b.L,
    b.C * Math.cos((b.h * Math.PI) / 180),
    b.C * Math.sin((b.h * Math.PI) / 180),
  ]
  const goal = target + 0.03
  for (let i = 0; i <= 200; i++) {
    const t = i / 200
    const lab = fromLab.map((v, k) => v + (towardLab[k] - v) * t)
    const rgb = oklabToRgb(...lab)
    if (contrast(rgb, bg) >= goal || t >= 1) return rgb
  }
  return towardRgb
}

/* ---- theme derivation -----------------------------------------------------
 * From one OKLCH hue+chroma, the four roles the design system actually needs:
 * the accent itself, its hover, a pale/deep wash for subtle backgrounds, and
 * the text colour that sits on a solid accent fill.
 */

// An OKLCH chroma this low is a grey wearing a hue label; the server declines
// those before storing a seed, and this declines any that reach the client
// anyway (a hand-edited row, a stale payload).
const MIN_CHROMA = 0.025

function deriveTheme(L, C, h) {
  const white = [1, 1, 1]
  const darkGround = [0x14 / 255, 0x17 / 255, 0x1d / 255]

  const accentLight = fitContrast(L, C, h, white, 4.5, false)
  const accentDark = fitContrast(L, C, h, darkGround, 4.5, true)
  const { L: La } = rgbToOklch(...accentLight)
  const { L: Ld } = rgbToOklch(...accentDark)

  const hoverLight = oklchToRgb(clamp(La - 0.07, 0.03, 0.97), C * 0.85, h)
  const hoverDark = oklchToRgb(clamp(Ld + 0.06, 0.03, 0.97), C * 0.95, h)

  // Subtle sits far enough from the accent that accent-coloured text reads on
  // top of it — a near-white wash in light mode, a near-black one in dark —
  // which is why this fades toward the true endpoint colour rather than
  // shifting lightness at fixed chroma (see fitMixToward).
  const subtleLight = fitMixToward(accentLight, white, accentLight, 4.5)
  const subtleDark = fitMixToward(accentDark, [0, 0, 0], accentDark, 4.5)

  // White text on accentLight is the same pair, in the same order, as the
  // contrast check accentLight was just fit against — always legible.
  const fgLight = white
  // accentDark is fit light/pastel against a dark page, so it needs dark text.
  const fgDark = fitMixToward(accentDark, [0, 0, 0], accentDark, 4.5)

  return {
    hue: h,
    light: {
      accent: hex(accentLight),
      hover: hex(hoverLight),
      subtle: hex(subtleLight),
      fg: hex(fgLight),
    },
    dark: {
      accent: hex(accentDark),
      hover: hex(hoverDark),
      subtle: hex(subtleDark),
      fg: hex(fgDark),
    },
  }
}

/* ---- entry point ---------------------------------------------------------- */

function parseSeed(seed) {
  const m = /^#?([0-9a-f]{6})$/i.exec(String(seed || '').trim())
  if (!m) return null
  const n = Number.parseInt(m[1], 16)
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255]
}

/**
 * The eight-token theme for a stored accent seed, or null when the seed is
 * absent, malformed, or too grey to theme a page with.
 */
export function themeFromSeed(seed) {
  const rgb = parseSeed(seed)
  if (!rgb) return null
  const { L, C, h } = rgbToOklch(...rgb)
  if (C < MIN_CHROMA) return null
  return deriveTheme(L, C, h)
}
