import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { apiClient } from '../api'

/**
 * Notifications: the app messaging one account, and the owner messaging many.
 *
 * A broadcast is fanned out to a row per recipient server-side, so this is just
 * "my messages" plus an unread count — no audience resolution on the client.
 * Reading clears the count, which the navbar dot reads from the same key.
 */

export const notificationsKey = ['notifications']

export function useNotifications() {
  return useQuery({
    queryKey: notificationsKey,
    queryFn: () => apiClient.getNotifications(),
    // The one query that must notice a change it did not cause. Everything else
    // is invalidated by its own mutation, but a notification arrives from
    // somewhere else, so poll while the tab is open and refetch when a phone
    // comes back to it. The global defaults turn focus-refetch off precisely
    // because of the big galleries; here it is the whole point.
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
  })
}

export function useMarkNotificationsRead() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.markNotificationsRead(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationsKey }),
  })
}

export function useBroadcastNotification() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => apiClient.broadcastNotification(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationsKey }),
  })
}

/** Remove one of your own normal notifications. Pinned ones have no row to remove. */
export function useDismissNotification() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => apiClient.dismissNotification(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationsKey }),
  })
}

/** Owner only: remove a notification from everyone's inbox. */
export function useDeleteNotification() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (data) => apiClient.deleteNotification(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: notificationsKey }),
  })
}
