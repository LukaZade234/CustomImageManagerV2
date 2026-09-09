import Button from './Button'
import Modal from './Modal'

/**
 * A confirmation step for actions that are awkward to undo.
 *
 * Exists because this codebase has no window.confirm anywhere — the browser
 * dialog cannot be styled, cannot be themed, and blocks the whole page — and
 * because bulk removal previously had no confirmation at all.
 */
export default function ConfirmDialog({
  title,
  body,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'primary',
  onConfirm,
  onCancel,
}) {
  return (
    <Modal
      onClose={onCancel}
      title={title}
      titleId="confirm-dialog-title"
      size="sm"
      footer={
        <>
          <Button onClick={onCancel}>{cancelLabel}</Button>
          <Button variant={variant} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {body}
    </Modal>
  )
}
