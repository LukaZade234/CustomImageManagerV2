import { useEffect, useRef, useState } from 'react'
import { Button, Card, EmptyState, Field, Input, SegmentedControl } from '../components/ui'
import { useMe } from '../queries/me'
import {
  useBroadcastNotification,
  useMarkNotificationsRead,
  useNotifications,
} from '../queries/notifications'
import { useStore } from '../store/useStore'

/**
 * Notifications: a plain list of messages to you, newest first.
 *
 * Two kinds arrive here — the app telling you something about your own account
 * (a role change, and later a removal), and a message an owner sent to everyone
 * or to moderators. Nothing is a task: the list is read, not worked. The owner
 * gets a small compose form at the top; everyone else just gets the list.
 */

const AUDIENCES = [
  { value: 'everyone', label: 'Everyone' },
  { value: 'moderators', label: 'Moderators' },
]

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function ComposeCard() {
  const addToast = useStore((s) => s.addToast)
  const broadcast = useBroadcastNotification()
  const [audience, setAudience] = useState('everyone')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')

  const send = async (e) => {
    e.preventDefault()
    if (!title.trim() || broadcast.isPending) return
    try {
      const res = await broadcast.mutateAsync({ audience, title: title.trim(), body: body.trim() })
      addToast(`Sent to ${res.sent} ${res.sent === 1 ? 'person' : 'people'}`, 'success')
      setTitle('')
      setBody('')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  return (
    <Card as="section" padding="lg">
      <h2 className="section-heading">Send a notification</h2>
      <p className="text-meta profile-lead">
        A message from you, delivered to every recipient's notifications. Everyone, or moderators
        only.
      </p>
      <form className="notification-compose" onSubmit={send}>
        <Field label="Send to" htmlFor="notification-audience">
          <SegmentedControl
            name="notification-audience"
            label="Audience"
            value={audience}
            onChange={setAudience}
            options={AUDIENCES}
          />
        </Field>
        <Field label="Title" htmlFor="notification-title" className="full-width">
          <Input
            id="notification-title"
            type="text"
            value={title}
            maxLength={200}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="A one-line summary"
            required
          />
        </Field>
        <Field label="Message" htmlFor="notification-body" className="full-width">
          <textarea
            id="notification-body"
            className="ui-input notification-compose__body"
            value={body}
            maxLength={2000}
            rows={5}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Optional detail"
          />
        </Field>
        <div className="edit-actions">
          <Button variant="primary" type="submit" disabled={broadcast.isPending || !title.trim()}>
            {broadcast.isPending ? 'Sending…' : 'Send'}
          </Button>
        </div>
      </form>
    </Card>
  )
}

export default function NotificationsPage() {
  const { data: me } = useMe()
  const { data, isPending, isError, error, refetch } = useNotifications()
  const markRead = useMarkNotificationsRead()
  const marked = useRef(false)

  // Opening the page is reading it. Guarded so it fires once per visit rather
  // than on every render the invalidated query produces.
  useEffect(() => {
    if (data?.unread > 0 && !marked.current) {
      marked.current = true
      markRead.mutate()
    }
  }, [data?.unread, markRead])

  const items = data?.items ?? []

  return (
    <Card as="section" padding="lg">
      <h1 className="page-title">Notifications</h1>

      {me?.is_owner && <ComposeCard />}

      <div className="notification-list">
        {isError ? (
          <EmptyState
            title="Could not load notifications"
            description={error?.message}
            action={<Button onClick={refetch}>Try again</Button>}
          />
        ) : isPending ? (
          <p className="text-meta" role="status">
            Loading…
          </p>
        ) : items.length === 0 ? (
          <EmptyState
            title="Nothing yet"
            description="Messages about your account, and announcements, will appear here."
          />
        ) : (
          items.map((notification) => (
            <article
              key={notification.id}
              className={`notification ${notification.read_at ? '' : 'notification--unread'}`}
            >
              <div className="notification__head">
                <h2 className="notification__title">{notification.title}</h2>
                <time className="notification__date text-meta" dateTime={notification.created_at}>
                  {formatDate(notification.created_at)}
                </time>
              </div>
              {notification.body && <p className="notification__body">{notification.body}</p>}
            </article>
          ))
        )}
      </div>
    </Card>
  )
}
