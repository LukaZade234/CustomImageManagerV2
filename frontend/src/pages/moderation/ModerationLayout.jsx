import { NavLink, Outlet } from 'react-router-dom'
import { Card } from '../../components/ui'

/**
 * The staff area, behind one set of tabs.
 *
 * Moderation outgrew a single page: the contributor surface, reported images
 * and the duplicate review are three different jobs, and the duplicate review
 * in particular was reachable only by a link tucked into the finder. Real routes
 * rather than local state, so a tab is linkable, survives a reload, and answers
 * the back button — the same reasoning as `ProfileLayout`.
 */

const TABS = [
  { to: '/profile/moderation', end: true, label: 'Users' },
  { to: '/profile/moderation/reports', label: 'Reports' },
  { to: '/profile/moderation/duplicates', label: 'Duplicates' },
]

export default function ModerationLayout() {
  return (
    <div className="moderation">
      <Card as="header" padding="lg" className="profile-header">
        <div>
          <h1 className="page-title">Moderation</h1>
          <p className="text-meta">
            Contributors, reported images and duplicate review. Staff only.
          </p>
        </div>
      </Card>

      <nav className="profile-tabs" aria-label="Moderation sections">
        {TABS.map((tab) => (
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
