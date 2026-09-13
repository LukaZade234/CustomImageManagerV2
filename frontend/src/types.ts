/**
 * Shapes returned by the Flask API.
 *
 * A few API shapes, kept as the seed for the incremental TypeScript adoption
 * (allowJs/checkJs). Nothing imports the file yet, so it is a record rather than
 * a contract; when a file is converted to `.ts`/`.tsx` these are the shapes to
 * type against. `Character` and `ApiError` are current; the two endpoint types
 * below are historical.
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
 * Historical: the endpoint was retired in favour of `/api/stats` and
 * `/api/customs`, and has since been deleted. Nothing returns this shape.
 */
export type CustomImageMap = Record<string, string[]>

/**
 * `GET /api/last-updated` — character name to Unix timestamp (seconds, float).
 *
 * Historical: superseded by `/api/saved`, which returns each row's `updated_at`.
 * The endpoint has since been deleted.
 */
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
