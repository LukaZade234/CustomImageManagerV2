import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api'

/**
 * The character gallery as server state, so react-query owns its cache,
 * loading state, retry and invalidation. The store used to hold a map of
 * per-character rows plus a parallel loading map, and every change had to
 * remember to refetch it by hand; now a mutation just invalidates this key.
 */

/** Cache key for one character's custom images. */
export const characterImagesKey = (name) => ['character-images', name]

/**
 * The gallery payload, tolerated in both shapes it has shipped in: the current
 * `{rows, accentSeed, copiedIds, lastBatchIds}` and the bare array an older
 * response carried.
 */
export async function fetchCharacterImages(name) {
  const payload = await apiClient.getCustomImagesForChar(name)
  const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.rows) ? payload.rows : []
  const accentSeed = Array.isArray(payload) ? null : (payload?.accentSeed ?? null)
  const accentManual = Array.isArray(payload) ? false : Boolean(payload?.accentManual)
  // This viewer's own $ai history for this character, if any. Empty for a
  // signed-out visitor and for one who has never copied here.
  const copiedIds = Array.isArray(payload) ? [] : (payload?.copiedIds ?? [])
  const lastBatchIds = Array.isArray(payload) ? [] : (payload?.lastBatchIds ?? [])
  // What is left to claim on this character, and this viewer's own claim state.
  // `claimable` is null when there is nothing unowned, which is what hides the
  // banner; `myClaim` carries the pending/rejected state once one is filed.
  const claimable = Array.isArray(payload) ? null : (payload?.claimable ?? null)
  const myClaim = Array.isArray(payload) ? null : (payload?.myClaim ?? null)
  return { rows, accentSeed, accentManual, copiedIds, lastBatchIds, claimable, myClaim }
}

export function useCharacterImages(name) {
  return useQuery({
    queryKey: characterImagesKey(name),
    queryFn: () => fetchCharacterImages(name),
    enabled: Boolean(name),
  })
}

/**
 * Apply a new order to the cached rows, without waiting for the server.
 *
 * Reordering used to refetch the whole character after every single drop, so
 * moving a dozen images meant a dozen round trips and a dozen identical toasts
 * over the gallery being edited. The gallery renders from this cache, so
 * writing the order here is what makes a drop land; the POST that follows is
 * only persistence.
 *
 * Rows the caller did not mention — hidden ones, or anything uploaded while the
 * page was open — keep their relative order at the end, which is exactly what
 * `db.reorder_custom_images` does with the same list. Getting that rule wrong
 * here would show an order the next reload does not reproduce.
 */
export function applyOrderToCache(queryClient, name, urls) {
  queryClient.setQueryData(characterImagesKey(name), (old) => {
    if (!old) return old
    const byUrl = new Map(old.rows.map((row) => [row.url, row]))
    const ordered = urls.map((url) => byUrl.get(url)).filter(Boolean)
    const placed = new Set(ordered.map((row) => row.url))
    ordered.push(...old.rows.filter((row) => !placed.has(row.url)))
    return { ...old, rows: ordered }
  })
}

/**
 * Ask a moderator to give this character's unowned images to the caller.
 *
 * Filing grants nothing — it only puts a request in the moderation queue — but
 * it does change this viewer's claim state on the character, so the gallery is
 * refreshed to pick up the new `myClaim`.
 */
export function useClaimCharacter(name) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.claimCharacter(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: characterImagesKey(name) }),
  })
}
