import { Navigate } from 'react-router-dom'

import { useMe } from '../queries/me'

/**
 * Sends anyone who is not the owner back to the home page.
 *
 * The cut-over route is owner-only rather than moderator-only: reconciling and
 * deleting from the ImgChest account is operator work, not moderation, and a
 * plain moderator has no reason to see it. Like `RequireModerator`, the redirect
 * is deliberate so the route is indistinguishable from the catch-all, and the
 * endpoint enforces the role itself — this is convenience, not the boundary.
 *
 * Pending renders nothing rather than redirecting, so a cold load while the role
 * is still unknown does not bounce a legitimate owner.
 */
export default function RequireOwner({ children }) {
  const { data: me, isPending } = useMe()
  if (isPending) return null
  if (!me?.is_owner) return <Navigate to="/" replace />
  return children
}
