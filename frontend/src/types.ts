/**
 * Shapes returned by the Flask API.
 *
 * These describe the CURRENT (v1) contract. Phase 3 of the rework replaces
 * `CustomImageMap` with records carrying id / added_by / state, so this file is
 * the first place to update when the data model lands — and the reason
 * TypeScript was adopted: the frontend and backend are about to disagree about
 * these shapes, and nothing else would catch it.
 *
 * See docs/ROADMAP.md Phase 3 and docs/DECISIONS.md section 6.
 */

/** `GET /api/characters` */
export interface Character {
  name: string
  series: string
  /** Mudae claim rank, e.g. "#42" — a string, not a number. */
  rank: string
  /** Main image URL. Empty string when unset, never null. */
  image: string
}

/**
 * `GET /custom_images.json` — every character's images in one payload.
 *
 * Note this is the endpoint Phase 9 replaces: HomePage downloads the entire map
 * just to compute two summary numbers.
 */
export type CustomImageMap = Record<string, string[]>

/** `GET /api/last-updated` — character name to Unix timestamp (seconds, float). */
export type LastUpdatedMap = Record<string, number>

/** `GET /api/mudae/status` */
export interface MudaeStatus {
  configured: boolean
}

/** Standard error body. Most endpoints return this alongside a 4xx/5xx status. */
export interface ApiError {
  error: string
  details?: string[]
}

/** `POST /api/custom-image` — note 200 with a non-empty `errors` on partial failure. */
export interface AddCustomImageResult {
  success: boolean
  message: string
  links: string[]
  errors: string[]
}
