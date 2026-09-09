import { useState } from 'react'
import { Button, Modal } from './ui'

/**
 * Reporting is for objective problems only — wrong character, dead link, NSFW,
 * duplicate. Taste is what Hide is for, and offering "I don't like it" here is
 * how a report queue turns into a popularity contest (DECISIONS.md section 1).
 *
 * The wording says plainly what a report does, because a mechanism that removes
 * other people's work should never be a surprise.
 */
const REASONS = [
  { value: 'wrong_character', label: 'Wrong character', hint: 'Not the character on this page' },
  { value: 'dead_link', label: 'Broken image', hint: 'The link no longer loads' },
  { value: 'nsfw', label: 'NSFW', hint: 'Not safe for this library' },
  { value: 'duplicate', label: 'Duplicate', hint: 'Already here, same picture' },
]

export default function ReportDialog({ onSubmit, onCancel }) {
  const [reason, setReason] = useState(null)

  return (
    <Modal
      onClose={onCancel}
      title="Report this image"
      titleId="report-dialog-title"
      size="sm"
      footer={
        <>
          <Button onClick={onCancel}>Cancel</Button>
          <Button variant="danger" disabled={!reason} onClick={() => onSubmit(reason)}>
            Report
          </Button>
        </>
      }
    >
      <p className="report-dialog__lead">
        Only for problems anyone would agree on. If you simply do not want to see it,{' '}
        <strong>Hide</strong> it instead — that affects nobody else.
      </p>
      <fieldset className="report-dialog__reasons">
        <legend className="sr-only">Reason</legend>
        {REASONS.map((option) => (
          <label
            key={option.value}
            className={`report-dialog__reason ${reason === option.value ? 'is-selected' : ''}`}
          >
            <input
              type="radio"
              name="report-reason"
              value={option.value}
              checked={reason === option.value}
              onChange={() => setReason(option.value)}
            />
            <span>
              <strong>{option.label}</strong>
              <span className="report-dialog__hint">{option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <p className="report-dialog__note">
        One more report from a different person will remove it. Removal is never permanent — anyone
        can restore it from the Removed list.
      </p>
    </Modal>
  )
}
