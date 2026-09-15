import { Badge, Button } from '../../components/ui'

/**
 * The selected contributor's header: who they are, how much they have done, and
 * the actions that act on the *person*.
 *
 * Every button is inert in phase 1 — the logic (what "suspended" even means for
 * a cookie identity) is its own decision, and the placement is worth settling
 * first. They are rendered disabled rather than hidden so the layout is real.
 */

/** "12 Jan 2026" reads better than an ISO string in a stat block. */
function formatDate(iso) {
  if (!iso) return '—'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

/** "3 days ago" for the last-activity stat. */
function relativeDay(iso) {
  if (!iso) return '—'
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return '—'
  const days = Math.floor((Date.now() - then.getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  const months = Math.floor(days / 30)
  return months === 1 ? 'a month ago' : `${months} months ago`
}

const ACTIONS = [{ label: 'Warn' }, { label: 'Suspend' }, { label: 'Ban', variant: 'danger' }]

export default function UserProfile({ user }) {
  const stats = [
    { label: 'Images', value: user.added },
    { label: 'Removed', value: user.removed },
    { label: 'Joined', value: formatDate(user.created_at) },
    { label: 'Last active', value: relativeDay(user.last_at) },
  ]

  return (
    <div className="moderation-profile moderation-profile--split">
      <div className="moderation-profile__identity">
        <div className="moderation-profile__id">
          <h2 className="section-heading moderation-profile__name">{user.handle}</h2>
          {user.role !== 'user' && <Badge tone="neutral">{user.role}</Badge>}
          {user.signed_in && <Badge tone="neutral">Discord</Badge>}
        </div>

        <div className="moderation-profile__actions">
          {ACTIONS.map((action) => (
            <Button
              key={action.label}
              size="sm"
              variant={action.variant ?? 'secondary'}
              disabled
              title="Not wired up yet"
            >
              {action.label}
            </Button>
          ))}
        </div>

        <p className="moderation-profile__note text-meta">Actions are not wired up yet.</p>
      </div>

      <dl className="moderation-profile__stats">
        {stats.map((stat) => (
          <div key={stat.label} className="moderation-profile__stat">
            <dt className="text-meta">{stat.label}</dt>
            <dd className="tabular">{stat.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
