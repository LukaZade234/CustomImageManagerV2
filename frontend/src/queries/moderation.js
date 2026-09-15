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

export function useModerationUserImages({ ref, state, character, page, enabled = true }) {
  return useQuery({
    queryKey: moderationUserImagesKey(ref, { state, character, page }),
    queryFn: () => apiClient.listModerationUserImages({ ref, state, character, page }),
    // Gated by the Images tab: opening a contributor on Info should not fetch
    // their gallery, and the counts it needs come from the contributor list.
    enabled: Boolean(ref) && enabled,
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

export function useModerationUserCharacters({
  ref,
  state,
  character,
  sort,
  order,
  page,
  enabled = true,
}) {
  return useQuery({
    queryKey: moderationUserCharactersKey(ref, { state, character, sort, order, page }),
    queryFn: () =>
      apiClient.listModerationUserCharacters({ ref, state, character, sort, order, page }),
    enabled: Boolean(ref) && enabled,
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

/** The staff log of what has been sent this contributor, newest first. */
export const moderationHistoryKey = (ref) => ['moderation-history', ref]

export function useModerationHistory(ref) {
  return useQuery({
    queryKey: moderationHistoryKey(ref),
    queryFn: () => apiClient.listModerationHistory(ref),
    enabled: Boolean(ref),
  })
}

/**
 * Warn a contributor: one message to their inbox, and a line in their history.
 * The history list has changed, so refresh it.
 */
export function useWarnModerationUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ ref, title, body }) => apiClient.warnModerationUser(ref, { title, body }),
    onSuccess: (_result, variables) =>
      queryClient.invalidateQueries({ queryKey: moderationHistoryKey(variables.ref) }),
  })
}

/**
 * Suspend or ban: the message and the record, plus the account state. The list
 * carries the new status, so refresh it too.
 */
function useRestrictModerationUser(mutationFn) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: moderationHistoryKey(variables.ref) })
      queryClient.invalidateQueries({ queryKey: moderationUsersKey })
    },
  })
}

export function useSuspendModerationUser() {
  return useRestrictModerationUser(({ ref, title, body, days }) =>
    apiClient.suspendModerationUser(ref, { title, body, days }),
  )
}

export function useBanModerationUser() {
  return useRestrictModerationUser(({ ref, title, body }) =>
    apiClient.banModerationUser(ref, { title, body }),
  )
}

/** Owner-only: lift a suspension or ban. */
export function useLiftModerationUser() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (ref) => apiClient.liftModerationUser(ref),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: moderationUsersKey })
      queryClient.invalidateQueries({ queryKey: ['moderation-history'] })
    },
  })
}

/** Owner-only: remove a moderation record, and the message it delivered. */
export function useDeleteModerationHistory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id) => apiClient.deleteModerationHistory(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['moderation-history'] }),
  })
}

/**
 * Owner-only: permanently delete an image — its ImgChest post, then a tombstone.
 * Both work views have lost a row, and the contributor counts have changed.
 */
export function usePurgeModerationImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ character, url }) => apiClient.purgeCustomImage(character, url),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['moderation-user-images'] })
      queryClient.invalidateQueries({ queryKey: ['moderation-user-characters'] })
      queryClient.invalidateQueries({ queryKey: moderationUsersKey })
    },
  })
}
