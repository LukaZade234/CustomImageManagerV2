import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api'

/**
 * Who the server thinks we are: handle, role, sign-in state, settings — never
 * the identity id.
 */

export const meKey = ['me']

export function useMe() {
  return useQuery({
    queryKey: meKey,
    queryFn: () => apiClient.getMe(),
    // `me` carries the role, and a role is handed out by someone else. The
    // navbar keeps this query mounted for the life of the tab, so it never
    // refetches on navigation, and the global "no focus refetch" (there for the
    // galleries) would leave a promoted moderator staring at a profile with no
    // Moderation tab until they happened to reload. It is a tiny payload; fetch
    // it on focus so a change made elsewhere arrives on its own.
    refetchOnWindowFocus: true,
  })
}

/**
 * Saving a preference folds the server's authoritative settings straight back
 * into the `me` cache, without a second round trip.
 *
 * The character-accent switch gates what a character page derives and reads it
 * from `me.settings`, so a preference that only took effect on the next page
 * load would look broken. The PATCH response is already the new state.
 */
export function useUpdateSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (settings) => apiClient.updateSettings(settings),
    onSuccess: (result) => {
      queryClient.setQueryData(meKey, (old) =>
        old && result?.settings
          ? { ...old, settings: { ...old.settings, ...result.settings } }
          : old,
      )
    },
  })
}

/**
 * Hand this browser a fresh anonymous identity.
 *
 * Not a delete: the account and everything it owns stays, and signing in again
 * reaches it. Saved characters are per identity, so both `me` and `saved` have
 * to be refetched rather than left showing the previous person's data.
 */
export function useSignOut() {
  const queryClient = useQueryClient()
  return async () => {
    await apiClient.logout()
    // The identity changed, so every server answer is now about someone else:
    // `me`, saved, the profile lists, and `is_mine` on a gallery. Invalidate all
    // of it rather than listing the keys that happen to exist today.
    await queryClient.invalidateQueries()
  }
}
