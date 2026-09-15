/**
 * The working row stores its card traits as two gender booleans and one pool
 * label ("Game & Animanga"), while the editor offers the four pool facets the
 * Add form uses. These are the two directions of that mapping.
 *
 * The label is the card's own caption, normalised the same way
 * `scripts.backfill_character_traits.pool_label` writes it, so a round trip
 * through the editor cannot drift from what the backfill would derive.
 */

const ANIMANGA = /animanga/i
const GAME = /\bgame\b/i

/** The facet keys a stored pair of genders and a pool label amount to. */
export function traitsToKeys(isFemale, isMale, pools) {
  const keys = []
  if (isFemale) keys.push('waifu')
  if (isMale) keys.push('husbando')
  const label = pools || ''
  if (ANIMANGA.test(label)) keys.push('anime')
  if (GAME.test(label)) keys.push('game')
  return keys
}

/** The pool label the card prints, from the roulette facet keys. */
export function poolLabel(keys) {
  const anime = keys.includes('anime')
  const game = keys.includes('game')
  if (anime && game) return 'Game & Animanga'
  if (anime) return 'Animanga'
  if (game) return 'Game'
  return ''
}

/** The stored traits the facet keys amount to. */
export function keysToTraits(keys) {
  return {
    is_female: keys.includes('waifu'),
    is_male: keys.includes('husbando'),
    pools: poolLabel(keys),
  }
}
