import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api'

/**
 * Hidden images as server state.
 *
 * This tab used to fetch with a raw `useEffect` + `apiClient`, which opted it
 * out of the app's invalidation: signing out changes the identity, so every
 * server answer is now about someone else, and react-query refetches — but a
 * hand-rolled fetch does not. The image was still hidden from *you*; this was
 * the previous person's list left on screen.
 */

export const hiddenKey = ['hidden']

export function useHiddenImages() {
  return useQuery({
    queryKey: hiddenKey,
    queryFn: async () => {
      const rows = await apiClient.getMyHidden()
      return Array.isArray(rows) ? rows : []
    },
  })
}

export function useUnhideImage() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (id) => apiClient.unhideImages([id]),
    // Drop the row from the list on success rather than refetching: the server
    // has confirmed it, and the list is otherwise unchanged.
    onSuccess: (_data, id) =>
      queryClient.setQueryData(hiddenKey, (rows) => (rows ?? []).filter((r) => r.id !== id)),
  })
}
