/**
 * Link-preview metadata for a character page, built on the edge.
 *
 * Discord's crawler does not run JavaScript, so the SPA shell it fetches shows
 * one generic title and no image for every character. A Cloudflare Pages
 * Function (see `functions/character/[name].ts`) intercepts `/character/*`,
 * asks the API for the character, and splices a small block of meta tags into
 * the served HTML before it reaches the crawler.
 *
 * Everything here is pure so it can be tested without the edge runtime — the
 * escaping and the fallbacks are the parts that matter, and they are the parts
 * a Worker cannot exercise locally.
 */

/** The API's `find_character` payload, narrowed to what a preview needs. */
export interface CharacterMeta {
  name: string
  series: string
  image: string
  image_thumb: string
  custom_count: number
  in_library: boolean
}

/**
 * Escape a value for use inside an HTML attribute (double-quoted).
 *
 * Character names and series are user-supplied: an unescaped `"` truncates the
 * tag, and `<` can open an element. `&` must be replaced first or it would
 * double-escape the entities the later replacements introduce.
 */
export function escapeAttr(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

/**
 * Where to load a portrait from, mirroring the SPA's `portraitUrl`: the mirrored
 * WebP on the image CDN when the server sent a key, otherwise the stored
 * original. Returns '' when there is nothing to show, so the caller can omit
 * `og:image` rather than emit a broken one.
 */
export function portraitUrl(
  character: Pick<CharacterMeta, 'image' | 'image_thumb'>,
  imageBase: string,
): string {
  const { image, image_thumb } = character
  if (image_thumb && imageBase) {
    return `${imageBase.replace(/\/$/, '')}/${image_thumb.replace(/^\/+/, '')}`
  }
  return image ?? ''
}

/** "12 custom images for Mudae" — the description, which carries the count. */
export function description(character: Pick<CharacterMeta, 'series' | 'custom_count'>): string {
  const count = character.custom_count
  const noun = count === 1 ? 'custom image' : 'custom images'
  const series = character.series ? `${character.series} · ` : ''
  return `${series}${count} ${noun} for Mudae`
}

/**
 * The meta block to splice into the shell's `<head>`, or '' when the character
 * is unknown or has nothing worth previewing.
 *
 * `pageUrl` must be absolute — crawlers ignore a relative `og:url`. `image`
 * is optional: a character with no portrait yields a text-only card, which is
 * still better than the generic one every route currently shows.
 */
export function buildMetaTags(
  character: CharacterMeta | null,
  opts: { pageUrl: string; imageBase: string },
): string {
  if (!character) return ''
  const title = `${character.name} — ImgManager`
  const desc = description(character)
  const image = portraitUrl(character, opts.imageBase)
  const tags = [
    `<meta property="og:title" content="${escapeAttr(title)}">`,
    `<meta property="og:description" content="${escapeAttr(desc)}">`,
    `<meta property="og:url" content="${escapeAttr(opts.pageUrl)}">`,
    '<meta property="og:type" content="website">',
    '<meta name="twitter:card" content="summary_large_image">',
  ]
  if (image) {
    tags.push(`<meta property="og:image" content="${escapeAttr(image)}">`)
    tags.push(`<meta name="twitter:image" content="${escapeAttr(image)}">`)
  }
  return tags.join('\n    ')
}

/**
 * Splice a block into an HTML document's head, immediately before `</head>`.
 * Returns the document unchanged if there is no head to splice into, so a
 * surprise in the shell degrades to today's behaviour rather than a broken page.
 */
export function injectIntoHead(html: string, tags: string): string {
  if (!tags) return html
  const at = html.indexOf('</head>')
  if (at === -1) return html
  return `${html.slice(0, at)}    ${tags}\n  ${html.slice(at)}`
}
