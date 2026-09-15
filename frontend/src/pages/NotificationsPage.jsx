import { useEffect, useRef, useState } from 'react'
import {
  Badge,
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Input,
  SegmentedControl,
} from '../components/ui'
import { useMe } from '../queries/me'
import {
  useBroadcastNotification,
  useDeleteNotification,
  useDismissNotification,
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
 *
 * A message can be **pinned**. A pin is not delivered per recipient: it is one
 * global announcement that every current and future account sees, and nobody can
 * dismiss it. An ordinary message is yours alone to dismiss, and the owner can
 * delete a broadcast from every inbox at once.
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
  const [pinned, setPinned] = useState(false)
  const bodyRef = useRef(null)

  // The message wraps and the box grows a line at a time as it fills, so a long
  // message is never hidden past the end of a fixed one-line field. Height is
  // reset first so it can also shrink when text is deleted.
  // biome-ignore lint/correctness/useExhaustiveDependencies: body is the trigger, not an input
  useEffect(() => {
    const el = bodyRef.current
    if (!el) return
    el.style.height = 'auto'
    el.style.height = `${el.scrollHeight}px`
  }, [body])

  const send = async (e) => {
    e.preventDefault()
    if (!title.trim() || broadcast.isPending) return
    try {
      const res = await broadcast.mutateAsync({
        audience,
        title: title.trim(),
        body: body.trim(),
        pinned,
      })
      addToast(`Sent to ${res.sent} ${res.sent === 1 ? 'person' : 'people'}`, 'success')
      setTitle('')
      setBody('')
      setPinned(false)
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  return (
    <form className="ui-card nc-bar" onSubmit={send}>
      {/* The visible form is one line; the description lives for assistive tech
          rather than as a paragraph that pushes the card a third of a screen
          tall before anything is typed. */}
      <h2 className="sr-only">Send a notification</h2>
      <p className="sr-only">
        A message from you, delivered to every recipient's notifications. Everyone, or moderators
        only.
      </p>
      <div className="nc-bar__row">
        <Input
          className="nc-bar__title"
          type="text"
          value={title}
          maxLength={200}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="Notification title"
          aria-label="Notification title"
          required
        />
        <SegmentedControl
          name="notification-audience"
          label="Audience"
          value={audience}
          onChange={setAudience}
          options={AUDIENCES}
        />
        <Button variant="primary" type="submit" disabled={broadcast.isPending || !title.trim()}>
          {broadcast.isPending ? 'Sending…' : 'Send'}
        </Button>
      </div>
      <textarea
        ref={bodyRef}
        className="ui-input nc-bar__msg"
        value={body}
        maxLength={2000}
        rows={1}
        onChange={(e) => setBody(e.target.value)}
        placeholder="Add a message (optional)"
        aria-label="Message (optional)"
      />
      <label className="nc-bar__pin">
        <input
          type="checkbox"
          checked={pinned}
          onChange={(e) => setPinned(e.target.checked)}
          aria-describedby="pin-hint"
        />
        <span id="pin-hint">
          Pin — always shown, even to accounts made later, and it cannot be dismissed
        </span>
      </label>
    </form>
  )
}

export default function NotificationsPage() {
  const { data: me } = useMe()
  const { data, isPending, isError, error, refetch } = useNotifications()
  const markRead = useMarkNotificationsRead()
  const dismiss = useDismissNotification()
  const remove = useDeleteNotification()
  const addToast = useStore((s) => s.addToast)
  const marked = useRef(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  // Opening the page is reading it. Guarded so it fires once per visit rather
  // than on every render the invalidated query produces.
  useEffect(() => {
    if (data?.unread > 0 && !marked.current) {
      marked.current = true
      markRead.mutate()
    }
  }, [data?.unread, markRead])

  const items = data?.items ?? []
  const isOwner = Boolean(me?.is_owner)

  const handleDismiss = (notification) => {
    dismiss.mutate(
      { id: notification.id },
      {
        onSuccess: () => addToast('Notification dismissed', 'success'),
        onError: (err) => addToast(err.message, 'error'),
      },
    )
  }

  const handleDelete = () => {
    const target = deleteTarget
    setDeleteTarget(null)
    if (!target) return
    remove.mutate(
      { source: target.pinned ? 'pin' : 'notification', id: target.id },
      {
        onSuccess: (res) =>
          addToast(
            `Deleted for ${res.removed} ${res.removed === 1 ? 'person' : 'people'}`,
            'success',
          ),
        onError: (err) => addToast(err.message, 'error'),
      },
    )
  }

  return (
    <Card as="section" padding="lg">
      <h1 className="page-title">Notifications</h1>

      {isOwner && <ComposeCard />}

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
              key={`${notification.source}-${notification.id}`}
              className={`notification ${!notification.read_at ? 'notification--unread' : ''}`}
            >
              <div className="notification__head">
                <h2 className="notification__title">
                  {notification.title}
                  {notification.pinned && <Badge tone="neutral">Pinned</Badge>}
                </h2>
                <time className="notification__date text-meta" dateTime={notification.created_at}>
                  {formatDate(notification.created_at)}
                </time>
              </div>
              {notification.body && <p className="notification__body">{notification.body}</p>}
              <div className="notification__actions">
                {/* A pinned message cannot be dismissed; an ordinary one is the
                    recipient's own row to remove. */}
                {!notification.pinned && (
                  <Button size="sm" variant="ghost" onClick={() => handleDismiss(notification)}>
                    Dismiss
                  </Button>
                )}
                {isOwner && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setDeleteTarget(notification)}
                    title="Remove this notification for everyone"
                  >
                    Delete
                  </Button>
                )}
              </div>
            </article>
          ))
        )}
      </div>

      {deleteTarget && (
        <ConfirmDialog
          title="Delete this notification?"
          body={
            deleteTarget.pinned
              ? 'It will be removed from everyone. Pinned messages cannot be brought back.'
              : 'It will be removed from every recipient inbox.'
          }
          confirmLabel="Delete"
          variant="danger"
          onConfirm={handleDelete}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
    </Card>
  )
}
