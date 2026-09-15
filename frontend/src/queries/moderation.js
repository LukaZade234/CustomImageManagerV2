import { keepPreviousData, useQuery } from '@tanstack/react-query'

import { apiClient } from '../api'

/**
 * The moderation surface's server state, following `queries/me.js`: react-query
 * owns the cache, the loading state and the retry, and a filter change is a new
 * key rather than a manual refetch. Nothing here is a mutation — phase 1 is
 * read-only by design (see docs/MODERATION.md).
 */

export const moderationUsersKey = ['moderation-users']

/** The detail key is spread across exactly the inputs the request uses. */
export const moderationUserImagesKey = (ref, { state, character, page }) => [
  'moderation-user-images',
  ref,
  state,
  character || '',
  page,
]

export function useModerationUsers() {
  return useQuery({
    queryKey: moderationUsersKey,
    queryFn: () => apiClient.listModerationUsers(),
  })
}

export function useModerationUserImages({ ref, state, character, page }) {
  return useQuery({
    queryKey: moderationUserImagesKey(ref, { state, character, page }),
    queryFn: () => apiClient.listModerationUserImages({ ref, state, character, page }),
    enabled: Boolean(ref),
    // Keep the previous page on screen while the next loads, so paging does not
    // flash the skeleton over content that is still valid.
    placeholderData: keepPreviousData,
  })
}

export const moderationUserCharactersKey = (ref, { state, character, sort, order, page }) => [
  'moderation-user-characters',
  ref,
  state,
  character || '',
  sort,
  order,
  page,
]

export function useModerationUserCharacters({ ref, state, character, sort, order, page }) {
  return useQuery({
    queryKey: moderationUserCharactersKey(ref, { state, character, sort, order, page }),
    queryFn: () =>
      apiClient.listModerationUserCharacters({ ref, state, character, sort, order, page }),
    enabled: Boolean(ref),
    placeholderData: keepPreviousData,
  })
}
