import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '../api'

/**
 * Bookmarks as server state.
 *
 * `/api/saved` joins the library row into each bookmark, so the series, portrait
 * and recency arrive with the list. Saving and unsaving invalidate it rather
 * than refetching by hand, which is what kept the store's copy in sync.
 */

export const savedKey = ['saved']

export function useSavedCharacters() {
  return useQuery({
    queryKey: savedKey,
    queryFn: async () => {
      const saved = await apiClient.getSaved()
      return Array.isArray(saved) ? saved : []
    },
  })
}

export function useSaveCharacter() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (char) => apiClient.saveCharacter(char),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: savedKey }),
  })
}

export function useRemoveSaved() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (name) => apiClient.removeSaved(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: savedKey }),
  })
}
