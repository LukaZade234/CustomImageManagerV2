import { Navigate } from 'react-router-dom'

import { useMe } from '../queries/me'

/**
 * Sends anyone who is not a moderator or the owner back to the home page.
 *
 * The redirect is deliberate rather than a "not permitted" screen: it makes the
 * route indistinguishable from the `*` catch-all, so its existence is not
 * advertised to anyone probing. This is a convenience, not the boundary — the
 * endpoints enforce the role themselves and never trust the client.
 *
 * `me` is a fetch, so the pending state renders nothing rather than redirecting:
 * bouncing while the role is still unknown would lock a legitimate moderator out
 * on every cold load.
 */
export default function RequireModerator({ children }) {
  const { data: me, isPending } = useMe()
  if (isPending) return null
  if (!me?.is_moderator) return <Navigate to="/" replace />
  return children
}
