import { useCallback } from 'react'
import { useStore } from '../store/useStore'
import { Button, Modal } from './ui'

/**
 * Modal for upload/import errors: stays open until dismissed, full text selectable and copyable.
 */
export default function UploadErrorDialog({ title, body, onClose }) {
  const addToast = useStore((s) => s.addToast)

  const handleCopy = useCallback(async () => {
    const t = body || ''
    if (!t) {
      addToast('Nothing to copy', 'info')
      return
    }

    const copyWithExecCommandFallback = () => {
      const ta = document.createElement('textarea')
      ta.value = t
      ta.style.position = 'fixed'
      ta.style.left = '-9999px'
      document.body.appendChild(ta)
      ta.select()
      try {
        return document.execCommand('copy')
      } finally {
        document.body.removeChild(ta)
      }
    }

    if (navigator.clipboard?.writeText) {
      try {
        await navigator.clipboard.writeText(t)
        addToast('Copied to clipboard', 'success')
        return
      } catch {
        // Fall through to execCommand
      }
    }

    let ok = false
    try {
      ok = copyWithExecCommandFallback()
    } catch {
      ok = false
    }
    if (ok) {
      addToast('Copied to clipboard', 'success')
    } else {
      addToast(
        'Could not copy automatically. Select the text above and use Ctrl+C (or Cmd+C on Mac).',
        'error',
      )
    }
  }, [body, addToast])

  if (!body) return null

  return (
    <Modal
      onClose={onClose}
      title={title || 'Upload issue'}
      titleId="upload-error-dialog-title"
      className="upload-error-dialog"
      footer={
        <>
          <Button onClick={handleCopy}>Copy details</Button>
          <Button variant="primary" onClick={onClose}>
            Dismiss
          </Button>
        </>
      }
    >
      <p className="upload-error-dialog__hint">
        Text stays until you close this panel. Use Copy to grab the full message for support or
        debugging.
      </p>
      <textarea
        className="upload-error-dialog__body"
        readOnly
        value={body}
        aria-label="Error details"
        onFocus={(e) => e.target.select()}
      />
    </Modal>
  )
}
