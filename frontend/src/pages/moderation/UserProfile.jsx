import { useState } from 'react'
import { Badge, Button, ConfirmDialog, IconButton } from '../../components/ui'
import { moderationStatus } from '../../utils/moderationActions'
import ModerationDialog from './ModerationDialog'

/**
 * The selected contributor's header: who they are, how much they have done, the
 * actions that act on the *person*, and — for the owner alone — the role
 * change.
 *
 * Warn is live: it sends the person a message and logs it (see WarnDialog and
 * the moderation history below the header). Suspend and ban have no effect to
 * attach to yet — a ban is only meaningful once it stops the account uploading —
 * so they stay inert rather than send a notice that would not be true.
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

export default function UserProfile({
  user,
  canManageRoles = false,
  onChangeRole,
  onWarn,
  onSuspend,
  onBan,
  onLift,
  canLift = false,
}) {
  const [confirming, setConfirming] = useState(false)
  const [dialog, setDialog] = useState(null)
  const [sending, setSending] = useState(false)
  const [lifting, setLifting] = useState(false)
  const roleChange = roleChangeFor(user)

  const status = user.moderation_status
  const restriction = moderationStatus(status)
  const banned = status === 'banned'
  const handlerFor = { warn: onWarn, suspend: onSuspend, ban: onBan }

  // The dialog stays up on failure so the text is not lost; the page reports why.
  const send = async (values) => {
    setSending(true)
    const done = await handlerFor[dialog](values)
    setSending(false)
    if (done) setDialog(null)
  }

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
          {restriction && (
            <Badge tone={restriction.tone}>
              {status === 'suspended' && user.moderation_until
                ? `Suspended until ${formatDate(user.moderation_until)}`
                : restriction.label}
            </Badge>
          )}
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
          <Button size="sm" variant="secondary" onClick={() => setDialog('warn')}>
            Warn
          </Button>
          <Button
            size="sm"
            variant="secondary"
            disabled={banned}
            title={banned ? 'Already banned' : undefined}
            onClick={() => setDialog('suspend')}
          >
            Suspend
          </Button>
          <Button
            size="sm"
            variant="danger"
            disabled={banned}
            title={banned ? 'Already banned' : undefined}
            onClick={() => setDialog('ban')}
          >
            Ban
          </Button>
          {canLift && restriction && (
            <Button size="sm" variant="secondary" onClick={() => setLifting(true)}>
              Lift {restriction.label.toLowerCase()}
            </Button>
          )}
        </div>

        <p className="moderation-profile__note text-meta">
          Warn sends a message. Suspend and ban also stop the account changing anything.
        </p>
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

      {lifting && restriction && (
        <ConfirmDialog
          title={`Lift the ${restriction.label.toLowerCase()}?`}
          body={`${user.handle} will be able to contribute again.`}
          confirmLabel="Lift"
          onConfirm={() => {
            setLifting(false)
            onLift()
          }}
          onCancel={() => setLifting(false)}
        />
      )}

      {dialog && (
        <ModerationDialog
          action={dialog}
          handle={user.handle}
          sending={sending}
          onSend={send}
          onCancel={() => setDialog(null)}
        />
      )}
    </div>
  )
}
