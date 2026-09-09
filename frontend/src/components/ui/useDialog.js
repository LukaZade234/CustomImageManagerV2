import { useCallback, useEffect, useRef } from 'react'

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

/**
 * Modal behaviour shared by every dialog: scroll lock, focus on open, focus
 * restore on close, Escape to dismiss, and a Tab trap.
 *
 * All three dialogs previously reimplemented the first four of these
 * independently, and only ImageModal implemented the trap — so the other two
 * set aria-modal while letting Tab walk out into the page behind them.
 *
 * Returns props to spread onto the dialog element.
 */
export function useDialog({ onClose, enabled = true }) {
  const dialogRef = useRef(null)
  const prevActiveRef = useRef(null)

  const getFocusables = useCallback(() => {
    const root = dialogRef.current
    if (!root) return []
    return Array.from(root.querySelectorAll(FOCUSABLE)).filter(
      (el) => el.offsetParent !== null || el.getClientRects().length > 0,
    )
  }, [])

  useEffect(() => {
    if (!enabled) return undefined
    prevActiveRef.current = document.activeElement
    // Deferred: the dialog's children have not laid out on the first tick, so
    // querying for focusables immediately finds nothing.
    const t = setTimeout(() => {
      const list = getFocusables()
      if (list.length) list[0].focus()
      else dialogRef.current?.focus()
    }, 0)
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      clearTimeout(t)
      document.body.style.overflow = previousOverflow
      const prev = prevActiveRef.current
      if (prev && typeof prev.focus === 'function') prev.focus()
    }
  }, [enabled, getFocusables])

  useEffect(() => {
    if (!enabled) return undefined
    const handler = (e) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        onClose?.()
      }
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [enabled, onClose])

  const onKeyDown = useCallback(
    (e) => {
      if (e.key !== 'Tab') return
      const list = getFocusables()
      if (list.length === 0) return
      const first = list[0]
      const last = list[list.length - 1]
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else if (document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    },
    [getFocusables],
  )

  const onBackdropClick = useCallback(
    (e) => {
      if (e.target === e.currentTarget) onClose?.()
    },
    [onClose],
  )

  return { dialogRef, onKeyDown, onBackdropClick }
}
