import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

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

/**
 * Put one removed image back. Restoring is not destructive and the endpoint is
 * open to anyone, so this is a plain mutation whose only job is to refresh the
 * moderation lists once it lands.
 */
export function useRestoreModerationImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ character, url }) => apiClient.restoreImages(character, [url]),
    onSuccess: () => {
      // Prefix keys, so every page/sort/filter of both work views refreshes.
      queryClient.invalidateQueries({ queryKey: ['moderation-user-images'] })
      queryClient.invalidateQueries({ queryKey: ['moderation-user-characters'] })
      queryClient.invalidateQueries({ queryKey: moderationUsersKey })
    },
  })
}

/** Owner-only: promote a user to moderator or demote a moderator back. */
export function useSetModerationRole() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ref, role }) => apiClient.setModerationRole(ref, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: moderationUsersKey }),
  })
}
