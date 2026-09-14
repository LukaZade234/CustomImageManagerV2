import { useQuery } from '@tanstack/react-query'
import { apiClient } from '../api'

/** The landing page's totals and highlights, one query cached across visits. */
export const statsKey = ['stats']

export function useStats() {
  return useQuery({
    queryKey: statsKey,
    queryFn: () => apiClient.getStats(),
  })
}
