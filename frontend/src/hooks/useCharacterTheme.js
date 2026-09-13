import { useMemo } from 'react'
import { themeFromSeed } from '../utils/accentFromImage'

/**
 * A character's own colour theme, derived from the seed the server measured.
 *
 * The seed — the one colour a character is "about" — is computed server-side
 * from the portrait and the pooled gallery whenever the gallery changes, and
 * arrives with the character list and with the gallery rows (see
 * accent_extract.py). Nothing is decoded, fetched or cached here: a seed turns
 * into the eight contrast-fitted tokens in microseconds, so the derivation is
 * memoised per seed and the seed itself is the only cache key that exists.
 *
 * That is the whole point of the move. The first version of this hook measured
 * pixels in the browser and cached the answer in localStorage forever, which
 * is how a character could keep an accent computed by an algorithm that no
 * longer existed, and keep no accent at all through the arrival of the
 * thumbnails that would have given her one.
 *
 * A null seed (the server declined: greyscale or honestly two-coloured art)
 * yields a null theme, and the page keeps the system accent — see the
 * "Per-character accent" block in tokens.css.
 */

const themeBySeed = new Map()

export function useCharacterTheme(characterName, seed) {
  return useMemo(() => {
    if (!characterName || !seed) return null
    if (!themeBySeed.has(seed)) themeBySeed.set(seed, themeFromSeed(seed))
    return themeBySeed.get(seed)
  }, [characterName, seed])
}
