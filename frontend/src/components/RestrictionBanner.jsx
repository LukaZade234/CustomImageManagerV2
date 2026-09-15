import { useMe } from '../queries/me'
import { moderationStatus } from '../utils/moderationActions'

/**
 * The persistent notice a suspended or banned account sees on every page.
 *
 * A restriction cannot hide the site — browsing is public and anonymous — so it
 * removes the ability to change anything instead. This banner is how the person
 * learns that, since there is no email: they can still sign in and read, and it
 * disappears the moment an owner lifts the restriction. It is deliberately not
 * dismissible.
 */

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function RestrictionBanner() {
  const { data: me } = useMe()
  const status = me?.moderation_status
  if (!status) return null

  const meta = moderationStatus(status) ?? { label: 'Restricted', tone: 'danger' }
  const summary =
    status === 'banned'
      ? 'Your account is banned.'
      : me.moderation_until
        ? `Your account is suspended until ${formatDate(me.moderation_until)}.`
        : 'Your account is suspended.'

  return (
    <div className={`restriction-banner restriction-banner--${meta.tone}`} role="status">
      <div className="restriction-banner__inner">
        <strong className="restriction-banner__label">{meta.label}</strong>
        <span>
          {summary} You can browse, but nothing you change will be saved.
          {me.moderation_reason ? ` Reason: ${me.moderation_reason}` : ''}
        </span>
      </div>
    </div>
  )
}
