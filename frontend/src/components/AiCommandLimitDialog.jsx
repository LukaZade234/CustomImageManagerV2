import { useEffect, useRef, useCallback, useState } from 'react'
import { useStore } from '../store/useStore'
import { DISCORD_LIMIT_REGULAR, DISCORD_LIMIT_NITRO } from '../utils/aiCommandDiscord'

function copyButtonLabel(partIndex, totalParts) {
  if (totalParts <= 1) return 'Copy command'
  return `Copy command ${partIndex + 1}/${totalParts}`
}

/** @returns {Promise<boolean>} */
async function copyWithFallback(text, addToast) {
  if (!text) {
    addToast('Nothing to copy', 'info')
    return false
  }
  const fallback = () => {
    const ta = document.createElement('textarea')
    ta.value = text
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
      await navigator.clipboard.writeText(text)
      addToast('Copied to clipboard', 'success')
      return true
    } catch {
      /* fall through */
    }
  }
  if (fallback()) {
    addToast('Copied to clipboard', 'success')
    return true
  }
  addToast('Could not copy — select text manually (Ctrl+C / Cmd+C)', 'error')
  return false
}

/**
 * Shown when $ai command length >= 2000. Two card columns: Regular vs Nitro limits.
 */
export default function AiCommandLimitDialog({ charCount, nonNitroParts, nitroParts, onClose }) {
  const closeBtnRef = useRef(null)
  const announceTimerRef = useRef(null)
  const addToast = useStore((s) => s.addToast)
  const [announce, setAnnounce] = useState('')
  const [copiedKeys, setCopiedKeys] = useState(() => new Set())

  const copyPart = useCallback(
    async (partKey, text, screenReaderLabel) => {
      const ok = await copyWithFallback(text, addToast)
      if (ok) {
        setCopiedKeys((prev) => new Set([...prev, partKey]))
        if (announceTimerRef.current) clearTimeout(announceTimerRef.current)
        setAnnounce(`${screenReaderLabel} copied to clipboard`)
        announceTimerRef.current = setTimeout(() => {
          setAnnounce('')
          announceTimerRef.current = null
        }, 2000)
      }
    },
    [addToast]
  )

  useEffect(() => {
    document.body.style.overflow = 'hidden'
    const t = setTimeout(() => closeBtnRef.current?.focus(), 0)
    return () => {
      clearTimeout(t)
      document.body.style.overflow = ''
      if (announceTimerRef.current) clearTimeout(announceTimerRef.current)
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

  const dialogDescId = 'ai-command-limit-desc'

  return (
    <div
      className="upload-error-dialog-backdrop ai-command-limit-dialog-backdrop"
      role="presentation"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="upload-error-dialog ai-command-limit-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-command-limit-title"
        aria-describedby={dialogDescId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="ai-command-limit-dialog__header">
          <span className="ai-command-limit-dialog__header-icon" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
          </span>
          <h2 id="ai-command-limit-title" className="ai-command-limit-dialog__title">
            $ai command exceeds Discord length
          </h2>
        </div>

        <div id={dialogDescId} className="ai-command-limit-dialog__summary-strip">
          <strong>{charCount.toLocaleString()}</strong> characters — Discord allows <strong>{DISCORD_LIMIT_REGULAR.toLocaleString()}</strong> per
          message (<strong>{DISCORD_LIMIT_NITRO.toLocaleString()}</strong> with Nitro). Copy each block as a separate message.
        </div>

        <div className="ai-command-limit-dialog__body">
          <div className="ai-command-limit-dialog__columns">
            <section className="ai-command-limit-dialog__column-card" aria-label="Regular Discord">
              <h3 className="ai-command-limit-dialog__column-title">
                Regular <span className="ai-command-limit-dialog__limit-pill">{DISCORD_LIMIT_REGULAR.toLocaleString()} max</span>
              </h3>
              <p className="ai-command-limit-dialog__column-meta">
                {nonNitroParts.length} message{nonNitroParts.length === 1 ? '' : 's'}
              </p>
              <div className="ai-command-limit-dialog__column-scroll">
                <ul className="ai-command-limit-dialog__part-list">
                  {nonNitroParts.map((text, idx) => {
                    const label = copyButtonLabel(idx, nonNitroParts.length)
                    const partKey = `regular-${idx}`
                    const wasCopied = copiedKeys.has(partKey)
                    return (
                      <li key={`n-${idx}`}>
                        <button
                          type="button"
                          className={`action-btn secondary ai-command-limit-dialog__copy-btn${wasCopied ? ' ai-command-limit-dialog__copy-btn--copied' : ''}`}
                          aria-label={wasCopied ? `${label} — copied` : label}
                          onClick={() => copyPart(partKey, text, label)}
                        >
                          {label}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </section>

            <section className="ai-command-limit-dialog__column-card" aria-label="Discord Nitro">
              <h3 className="ai-command-limit-dialog__column-title">
                Nitro <span className="ai-command-limit-dialog__limit-pill">{DISCORD_LIMIT_NITRO.toLocaleString()} max</span>
              </h3>
              <p className="ai-command-limit-dialog__column-meta">
                {nitroParts.length} message{nitroParts.length === 1 ? '' : 's'}
              </p>
              <div className="ai-command-limit-dialog__column-scroll">
                <ul className="ai-command-limit-dialog__part-list">
                  {nitroParts.map((text, idx) => {
                    const label = copyButtonLabel(idx, nitroParts.length)
                    const partKey = `nitro-${idx}`
                    const wasCopied = copiedKeys.has(partKey)
                    return (
                      <li key={`t-${idx}`}>
                        <button
                          type="button"
                          className={`action-btn secondary ai-command-limit-dialog__copy-btn${wasCopied ? ' ai-command-limit-dialog__copy-btn--copied' : ''}`}
                          aria-label={wasCopied ? `${label} — copied` : label}
                          onClick={() => copyPart(partKey, text, label)}
                        >
                          {label}
                        </button>
                      </li>
                    )
                  })}
                </ul>
              </div>
            </section>
          </div>
        </div>

        <div className="ai-command-limit-dialog__footer upload-error-dialog__actions">
          <button ref={closeBtnRef} type="button" className="action-btn secondary" onClick={onClose}>
            Close
          </button>
        </div>

        <div className="ai-command-limit-dialog__sr-only" role="status" aria-live="polite" aria-atomic="true">
          {announce}
        </div>
      </div>
    </div>
  )
}
