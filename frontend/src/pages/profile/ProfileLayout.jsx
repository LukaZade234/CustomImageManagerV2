import { NavLink, Outlet } from 'react-router-dom'
import { Card } from '../../components/ui'
import { useMe } from '../../queries/me'

/**
 * Everything that belongs to you, behind one set of tabs.
 *
 * Saved used to be its own top-level page and the rest were not reachable at
 * all — hidden and removed images could only be found from the character page
 * holding them, so anyone who did not recall which character that was had no
 * way back. Collecting them here is the point; the tabs are how five lists fit
 * in one place without becoming one enormous page.
 *
 * Real routes rather than local state, so a tab is linkable, survives a reload,
 * and answers the back button.
 */

const TABS = [
  { to: '/profile', end: true, label: 'Profile' },
  { to: '/profile/saved', label: 'Saved' },
  { to: '/profile/history', label: 'History' },
  { to: '/profile/hidden', label: 'Hidden' },
  { to: '/profile/removed', label: 'Removed' },
]

/** The moderation surface is a staff tab, not topbar chrome. */
const MODERATION_TAB = { to: '/profile/moderation', label: 'Moderation' }

export default function ProfileLayout() {
  const { data: me } = useMe()
  const tabs = me?.is_moderator ? [...TABS, MODERATION_TAB] : TABS

  return (
    <div className="profile">
      <Card as="header" padding="lg" className="profile-header">
        <div>
          <h1 className="page-title">{me?.handle ?? 'Profile'}</h1>
          <p className="text-meta">
            {me?.signed_in
              ? 'Signed in with Discord.'
              : 'A name your browser was given. No account needed.'}
            {me?.is_moderator && ` Role: ${me.role}.`}
          </p>
        </div>
      </Card>

      <nav className="profile-tabs" aria-label="Profile sections">
        {tabs.map((tab) => (
          <NavLink
            key={tab.to}
            to={tab.to}
            end={tab.end}
            className={({ isActive }) => `profile-tab${isActive ? ' profile-tab--active' : ''}`}
          >
            {tab.label}
          </NavLink>
        ))}
      </nav>

      <Outlet />
    </div>
  )
}
