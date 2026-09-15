import { useState } from 'react'

import { Badge, Button, Field, Input, Modal } from '../../components/ui'

/**
 * The composer for a moderation message, opened from a person's Warn button.
 *
 * What the moderator writes is exactly what the recipient reads: a title and a
 * description, delivered to their notifications. It is not a private note — the
 * lead says so — and the same text is kept in their moderation history.
 *
 * The title is required; a warning with no words in it is not a warning. The
 * dialog is `warn`-shaped today (amber badge, "Send warning"), and the copy is
 * the only thing that would change to send a suspension or a ban.
 */
export default function WarnDialog({ handle, onSend, onCancel, sending = false }) {
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')

  const canSend = title.trim().length > 0 && !sending

  const submit = (event) => {
    event.preventDefault()
    if (!canSend) return
    onSend({ title: title.trim(), body: body.trim() })
  }

  return (
    <Modal
      onClose={onCancel}
      title={`Warn ${handle}`}
      titleId="warn-dialog-title"
      size="sm"
      footer={
        <>
          <Button onClick={onCancel} disabled={sending}>
            Cancel
          </Button>
          {/* type=button, and the click submits: a submit button carrying the
              `form` attribute is the one thing jsdom will not do, and the form's
              own onSubmit still gives Enter-in-a-field the same result. */}
          <Button variant="primary" onClick={submit} disabled={!canSend}>
            {sending ? 'Sending…' : 'Send warning'}
          </Button>
        </>
      }
    >
      <form className="warn-dialog" onSubmit={submit}>
        <p className="warn-dialog__lead text-meta">
          <Badge tone="warning">Warning</Badge> This sends {handle} a message in their inbox, and
          keeps a record in their moderation history.
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
              placeholder="What this warning is about"
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
              className="ui-input warn-dialog__message"
              value={body}
              maxLength={2000}
              rows={4}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Add the detail they need (optional)"
            />
          )}
        </Field>
      </form>
    </Modal>
  )
}
