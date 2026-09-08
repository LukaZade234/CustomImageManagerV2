import { useEffect, useRef, useCallback } from 'react'
import { useStore } from '../store/useStore'

/**
 * Modal for upload/import errors: stays open until dismissed, full text selectable and copyable.
 */
export default function UploadErrorDialog({ title, body, onClose }) {
  const closeBtnRef = useRef(null)
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
      addToast('Could not copy automatically. Select the text above and use Ctrl+C (or Cmd+C on Mac).', 'error')
    }
  }, [body, addToast])

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    const t = setTimeout(() => closeBtnRef.current?.focus(), 0)
    return () => {
      clearTimeout(t)
      document.body.style.overflow = ''
    }
  }, [])

  useEffect(() => {
    const h = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose()
      }
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onClose])

  if (!body) return null

  return (
    <div
      className="upload-error-dialog-backdrop"
      role="presentation"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="upload-error-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="upload-error-dialog-title"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="upload-error-dialog-title" className="upload-error-dialog__title">
          {title || 'Upload issue'}
        </h2>
        <p className="upload-error-dialog__hint">
          Text stays until you close this panel. Use Copy to grab the full message for support or debugging.
        </p>
        <textarea
          className="upload-error-dialog__body"
          readOnly
          value={body}
          aria-label="Error details"
          onFocus={(e) => e.target.select()}
        />
        <div className="upload-error-dialog__actions">
          <button type="button" className="action-btn secondary" onClick={handleCopy}>
            Copy details
          </button>
          <button ref={closeBtnRef} type="button" className="action-btn primary" onClick={onClose}>
            Dismiss
          </button>
        </div>
      </div>
    </div>
  )
}
