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
