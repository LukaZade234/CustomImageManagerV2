import { useStore } from '../store/useStore'

function ToastIcon({ type }) {
  if (type === 'success') {
    return (
      <span className="toast-icon toast-icon--success" aria-hidden>
        <svg
          aria-hidden="true"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.25"
          strokeLinecap="round"
          strokeLinejoin="round"
        >
          <path d="M20 6L9 17l-5-5" />
        </svg>
      </span>
    )
  }
  if (type === 'error') {
    return (
      <span className="toast-icon toast-icon--error" aria-hidden>
        <svg
          aria-hidden="true"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
      </span>
    )
  }
  return (
    <span className="toast-icon toast-icon--info" aria-hidden>
      <svg
        aria-hidden="true"
        width="20"
        height="20"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="16" x2="12" y2="12" />
        <line x1="12" y1="8" x2="12.01" y2="8" />
      </svg>
    </span>
  )
}

export default function Toast() {
  const toasts = useStore((s) => s.toasts)
  const removeToast = useStore((s) => s.removeToast)

  if (toasts.length === 0) return null

  return (
    <div id="toast-container" aria-live="polite" aria-relevant="additions">
      {/*
        A toast is an announcement, so it is a status region rather than a
        control. It used to be a div with role="button" that *contained* the
        Undo button -- a button inside a button, which is invalid and is why
        Undo needed stopPropagation to avoid also dismissing the toast. Clicking
        anywhere to dismiss is gone with it; toasts already disappear on their
        own after a few seconds, and the explicit control below is both
        discoverable and reachable by keyboard, which the old one was not.
      */}
      {toasts.map((t) => (
        <div key={t.id} className={`toast toast--${t.type || 'info'}`} role="status">
          <ToastIcon type={t.type} />
          <span className="toast-message">{t.msg}</span>
          {typeof t.onUndo === 'function' && (
            <button
              type="button"
              className="toast-undo"
              onClick={async () => {
                try {
                  await t.onUndo()
                } finally {
                  removeToast(t.id)
                }
              }}
            >
              {t.undoLabel || 'Undo'}
            </button>
          )}
          <button
            type="button"
            className="toast-dismiss"
            onClick={() => removeToast(t.id)}
            aria-label="Dismiss notification"
          >
            &times;
          </button>
        </div>
      ))}
    </div>
  )
}
