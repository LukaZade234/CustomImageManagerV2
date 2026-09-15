import { useState } from 'react'
import { Badge, Button, ConfirmDialog, IconButton } from '../../components/ui'

/**
 * The selected contributor's header: who they are, how much they have done, the
 * actions that act on the *person*, and — for the owner alone — the role
 * change.
 *
 * The person actions are inert in phase 1. The role change is live, and
 * owner-only: a moderator has every other power the owner has but may not
 * change roles, so the control is not rendered for them at all (the backend
 * enforces it regardless).
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

/** The role change offered for this account, if any. The owner is not mutable. */
function roleChangeFor(user) {
  if (user.role === 'user') {
    return {
      to: 'moderator',
      label: 'Promote to moderator',
      confirmLabel: 'Promote',
      variant: 'primary',
      title: 'Promote to moderator?',
      body: `${user.handle} will get the moderation surface and all its powers.`,
    }
  }
  if (user.role === 'moderator') {
    return {
      to: 'user',
      label: 'Remove moderator role',
      confirmLabel: 'Remove',
      variant: 'danger',
      title: 'Remove moderator role?',
      body: `${user.handle} will lose access to the moderation surface.`,
    }
  }
  return null
}

function PlusIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function MinusIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

const ACTIONS = [{ label: 'Warn' }, { label: 'Suspend' }, { label: 'Ban', variant: 'danger' }]

export default function UserProfile({ user, canManageRoles = false, onChangeRole }) {
  const [confirming, setConfirming] = useState(false)
  const roleChange = roleChangeFor(user)

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
          {canManageRoles && roleChange && (
            <IconButton
              label={roleChange.label}
              variant={roleChange.to === 'moderator' ? 'secondary' : 'danger'}
              onClick={() => setConfirming(true)}
            >
              {roleChange.to === 'moderator' ? <PlusIcon /> : <MinusIcon />}
            </IconButton>
          )}
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

      {confirming && roleChange && (
        <ConfirmDialog
          title={roleChange.title}
          body={roleChange.body}
          confirmLabel={roleChange.confirmLabel}
          variant={roleChange.variant}
          onConfirm={() => {
            setConfirming(false)
            onChangeRole(roleChange.to)
          }}
          onCancel={() => setConfirming(false)}
        />
      )}
    </div>
  )
}
