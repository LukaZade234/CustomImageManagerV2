/** Discord message limits for $ai paste (user-visible command string). */
export const DISCORD_LIMIT_REGULAR = 2000
export const DISCORD_LIMIT_NITRO = 4000

/**
 * Mudae's own cap: a character can take at most 100 custom images through
 * `$ai`. A command carrying more is rejected outright, so the app must never
 * build one -- the user would get a bot error and no explanation.
 */
export const MUDAE_AI_MAX_IMAGES = 100

/**
 * The images an `$ai` command may actually carry, in gallery order.
 *
 * Takes the first `MUDAE_AI_MAX_IMAGES` when the selection is larger, so "copy
 * everything" degrades to "copy the first 100" rather than to a rejected
 * command. Returns the URLs alongside how many were dropped, so the caller can
 * say so instead of silently discarding the rest.
 *
 * @param {string[]} urls
 * @returns {{urls: string[], dropped: number}}
 */
export function capAiImages(urls) {
  if (urls.length <= MUDAE_AI_MAX_IMAGES) return { urls, dropped: 0 }
  return { urls: urls.slice(0, MUDAE_AI_MAX_IMAGES), dropped: urls.length - MUDAE_AI_MAX_IMAGES }
}

/**
 * One ImgChest URL token as used in chat: `$` + full URL (never split).
 * @param {string} u raw URL or already with leading $
 */
function dollarToken(u) {
  const s = String(u ?? '')
  return s.startsWith('$') ? s : `$${s}`
}

/**
 * Build a single Mudae line: always `$ai <name> $<url1> $<url2> …`
 * Whole URLs only — never substring of a link.
 * @param {string} charName
 * @param {string[]} urls same URL strings as CharacterPage (no `$` prefix required)
 */
export function buildAiSegment(charName, urls) {
  const tokens = urls.map(dollarToken)
  return `$ai ${charName} ${tokens.join(' ')}`
}

/**
 * Same as CharacterPage: `$ai Name $url1 $url2 …`
 * @param {string} charName
 * @param {string[]} urls
 */
export function buildAiCommand(charName, urls) {
  return buildAiSegment(charName, urls)
}

/**
 * Split into multiple `$ai …` lines, each at most `maxLen` characters.
 * Only splits **between** whole URL tokens; a link is never cut in half.
 * Every returned string starts with `$ai `.
 * @param {string} charName
 * @param {string[]} urls
 * @param {number} maxLen
 * @returns {string[]}
 */
export function splitAiCommandForLimit(charName, urls, maxLen) {
  const tokens = urls.map(dollarToken)
  const parts = []
  let i = 0
  while (i < tokens.length) {
    const rest = tokens.slice(i)
    let take = 1
    const segment = buildAiSegment(charName, rest.slice(0, take))
    if (segment.length > maxLen) {
      parts.push(segment)
      i += 1
      continue
    }
    while (take < rest.length) {
      const trial = buildAiSegment(charName, rest.slice(0, take + 1))
      if (trial.length <= maxLen) take += 1
      else break
    }
    parts.push(buildAiSegment(charName, rest.slice(0, take)))
    i += take
  }
  return parts
}
