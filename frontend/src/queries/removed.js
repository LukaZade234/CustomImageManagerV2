import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api'

/**
 * Removed images as server state.
 *
 * Like the hidden tab, this used a raw `useEffect` fetch, so it took no part in
 * invalidation and kept showing the previous identity's rows after a sign-out.
 * See `queries/hidden.js` for the full note.
 */

export const removedKey = ['removed']

export function useRemovedImages() {
  return useQuery({
    queryKey: removedKey,
    queryFn: async () => {
      const rows = await apiClient.getMyRemoved()
      return Array.isArray(rows) ? rows : []
    },
  })
}

export function useRestoreImage() {
  const queryClient = useQueryClient()
  return useMutation({
    // Restore is addressed by character and URL, not by image id.
    mutationFn: ({ character, url }) => apiClient.restoreImages(character, [url]),
    // Drop the row on success rather than refetching: the server has confirmed
    // the restore, and the rest of the list is unchanged.
    onSuccess: (_data, { url }) =>
      queryClient.setQueryData(removedKey, (rows) => (rows ?? []).filter((r) => r.url !== url)),
  })
}
