/**
 * Link previews for character pages.
 *
 * Discord's crawler does not run JavaScript, so every character link pasted into
 * a channel rendered as the same generic card with no art. This Pages Function
 * intercepts `/character/*`, asks the API for that one character, and splices a
 * block of Open Graph / Twitter tags into the served shell before the crawler
 * sees it.
 *
 * It is deliberately all-or-nothing: if the API is slow, down, or does not know
 * the character, the shell is returned exactly as Cloudflare would have served
 * it. A failure degrades to today's behaviour — a plain card — never to a
 * broken page. The SPA itself is unaffected either way, since the tags only
 * change what crawlers read.
 *
 * Config (Pages → Settings → Environment variables):
 *   API_BASE_URL   e.g. https://api.example.com   (no trailing slash)
 *   IMAGE_BASE_URL e.g. https://images.example.com (the R2 custom domain)
 * Both also appear in `wrangler.jsonc` for local `wrangler pages dev`.
 */

import { buildMetaTags, type CharacterMeta, injectIntoHead } from '../_lib/metaTags'

interface Env {
  ASSETS: { fetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response> }
  API_BASE_URL?: string
  IMAGE_BASE_URL?: string
}

/** API lookup timeout. A crawler will not wait, so neither will we. */
const API_TIMEOUT_MS = 2500

async function lookupCharacter(name: string, apiBase: string): Promise<CharacterMeta | null> {
  if (!apiBase) return null
  const url = `${apiBase.replace(/\/$/, '')}/api/catalog/character?name=${encodeURIComponent(name)}`
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), API_TIMEOUT_MS)
  try {
    const resp = await fetch(url, { signal: controller.signal })
    if (!resp.ok) return null
    const data = (await resp.json()) as { found?: boolean; character?: CharacterMeta | null }
    return data?.found && data.character ? data.character : null
  } catch {
    // Timeout, DNS failure, or malformed JSON: fall back to the static shell.
    return null
  } finally {
    clearTimeout(timer)
  }
}

export const onRequest: PagesFunction<Env> = async (context) => {
  const { request, env, params } = context

  // Defensive: this handler is only meant to run for /character/*, and
  // `_routes.json` should scope it there. If it is ever invoked for another
  // path, pass the request straight through rather than answering it with the
  // root shell — that is what turns a routing mistake into "everything on the
  // site returns HTML", which the browser then fails to JSON.parse.
  if (!new URL(request.url).pathname.startsWith('/character/')) {
    return env.ASSETS.fetch(request)
  }

  // Fetch the shell explicitly by its root path rather than passing `request`
  // through: there is no dist/character/<name> file, so we depend on the asset
  // server resolving to index.html, which is a Pages-wide SPA-fallback setting
  // rather than a property of this request. A bare "/" is unambiguous.
  const shellUrl = new URL('/', request.url)
  const shell = await env.ASSETS.fetch(shellUrl)

  // Only HTML gets the treatment; a crawler requesting anything else is answered
  // by the asset server as normal.
  const contentType = shell.headers.get('content-type') || ''
  if (!contentType.includes('text/html')) return shell

  const name = Array.isArray(params.name) ? params.name.join('/') : String(params.name ?? '')
  const character = name ? await lookupCharacter(name, env.API_BASE_URL ?? '') : null

  const tags = buildMetaTags(character, {
    pageUrl: request.url,
    imageBase: env.IMAGE_BASE_URL ?? '',
  })
  if (!tags) return shell

  const body = injectIntoHead(await shell.text(), tags)
  const headers = new Headers(shell.headers)
  // The shell is no-cache by design (a stale SPA after deploy is worse than a
  // refetch); injecting does not change that, and deleting content-length is
  // required because the body length changed.
  headers.delete('content-length')
  return new Response(body, { status: shell.status, headers })
}
