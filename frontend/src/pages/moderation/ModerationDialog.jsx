import { useState } from 'react'

import { Badge, Button, Field, Input, Modal, Select } from '../../components/ui'
import { moderationAction } from '../../utils/moderationActions'

/**
 * The composer for a moderation action, opened from a contributor's Warn /
 * Suspend / Ban buttons.
 *
 * What the moderator writes is exactly what the recipient reads: a title and a
 * description, delivered to their notifications. It is not a private note — the
 * lead says so — and the same text is kept in their moderation history. A
 * suspension additionally carries a duration; a ban does not, being open-ended.
 *
 * Warn only sends a message. Suspend and ban also change what the account may
 * do; the copy names that difference rather than pretending they are the same.
 */

const DAY_OPTIONS = [
  { value: '1', label: '1 day' },
  { value: '3', label: '3 days' },
  { value: '7', label: '7 days' },
  { value: '30', label: '30 days' },
]

const CONSEQUENCE = {
  warn: 'This sends a message only — the account keeps full use of the site.',
  suspend: 'They will be able to browse, but every change will be refused until it ends.',
  ban: 'They will be able to browse, but every change will be refused until you lift it.',
}

export default function ModerationDialog({ action, handle, onSend, onCancel, sending = false }) {
  const meta = moderationAction(action) ?? { label: action, tone: 'neutral' }
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [days, setDays] = useState('3')

  const canSend = title.trim().length > 0 && !sending

  const submit = (event) => {
    event.preventDefault()
    if (!canSend) return
    onSend({
      title: title.trim(),
      body: body.trim(),
      ...(action === 'suspend' ? { days: Number(days) } : {}),
    })
  }

  return (
    <Modal
      onClose={onCancel}
      title={`${meta.label} ${handle}`}
      titleId="moderation-dialog-title"
      size="sm"
      footer={
        <>
          <Button onClick={onCancel} disabled={sending}>
            Cancel
          </Button>
          <Button
            variant={action === 'ban' ? 'danger' : 'primary'}
            onClick={submit}
            disabled={!canSend}
          >
            {sending ? 'Sending…' : `Send ${meta.label.toLowerCase()}`}
          </Button>
        </>
      }
    >
      <form className="moderation-dialog" onSubmit={submit}>
        <p className="moderation-dialog__lead text-meta">
          <Badge tone={meta.tone}>{meta.label}</Badge>
          {CONSEQUENCE[action] ?? `This sends ${handle} a message.`}
        </p>
        <Field label="Title" hint="The subject of the message.">
          {({ id, describedBy }) => (
            <Input
              id={id}
              aria-describedby={describedBy}
              type="text"
              value={title}
              maxLength={200}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="What this is about"
              autoComplete="off"
              autoFocus
            />
          )}
        </Field>
        <Field label="Description" hint="What needs to change, in your own words.">
          {({ id, describedBy }) => (
            <textarea
              id={id}
              aria-describedby={describedBy}
              className="ui-input moderation-dialog__message"
              value={body}
              maxLength={2000}
              rows={4}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Add the detail they need (optional)"
            />
          )}
        </Field>
        {action === 'suspend' && (
          <Field label="Duration">
            {({ id }) => (
              <Select id={id} value={days} onChange={(e) => setDays(e.target.value)}>
                {DAY_OPTIONS.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </Select>
            )}
          </Field>
        )}
      </form>
    </Modal>
  )
}
