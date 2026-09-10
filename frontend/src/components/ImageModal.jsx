import { useCallback, useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import { useDialog } from './ui'

const SWIPE_THRESHOLD_PX = 50

export default function ImageModal({ images, currentIndex, onClose, onPrev, onNext, onReport }) {
  const { dialogRef, onKeyDown, onBackdropClick } = useDialog({ onClose })
  const touchStartRef = useRef(null)

  useEffect(() => {
    const h = (e) => {
      if (e.key === 'ArrowLeft') onPrev()
      if (e.key === 'ArrowRight') onNext()
    }
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [onPrev, onNext])

  const onTouchStart = useCallback((e) => {
    const t = e.touches[0]
    if (!t) return
    touchStartRef.current = { x: t.clientX, y: t.clientY }
  }, [])

  const onTouchEnd = useCallback(
    (e) => {
      const start = touchStartRef.current
      touchStartRef.current = null
      if (!start) return
      const t = e.changedTouches[0]
      if (!t) return
      const dx = t.clientX - start.x
      const dy = t.clientY - start.y
      if (Math.abs(dy) > Math.abs(dx) && Math.abs(dy) > 45) return
      if (Math.abs(dx) < SWIPE_THRESHOLD_PX) return
      if (dx > 0) onPrev()
      else onNext()
    },
    [onPrev, onNext],
  )

  if (!images?.length) return null

  const img = images[currentIndex]
  const src = typeof img === 'string' ? img : img?.url
  if (!src) return null

  return createPortal(
    <div
      ref={dialogRef}
      className="image-modal"
      role="dialog"
      aria-modal="true"
      aria-label="Image viewer"
      tabIndex={-1}
      onKeyDown={onKeyDown}
      onClick={onBackdropClick}
      onTouchStart={onTouchStart}
      onTouchEnd={onTouchEnd}
    >
      <button type="button" className="image-modal-close" onClick={onClose} aria-label="Close">
        &times;
      </button>
      {currentIndex > 0 && (
        <button
          type="button"
          className="image-modal-nav image-modal-prev"
          onClick={onPrev}
          aria-label="Previous image"
        >
          &#10094;
        </button>
      )}
      {/*
        No click handler: useDialog's onBackdropClick already closes only when
        the click landed on the backdrop itself (e.target === e.currentTarget),
        so the stopPropagation that used to sit here could never have mattered.
      */}
      <img src={src} alt="" tabIndex={-1} />
      {currentIndex < images.length - 1 && (
        <button
          type="button"
          className="image-modal-nav image-modal-next"
          onClick={onNext}
          aria-label="Next image"
        >
          &#10095;
        </button>
      )}
      <div className="image-modal-counter" aria-live="polite">
        {currentIndex + 1} / {images.length}
      </div>
      {onReport && (
        <button
          type="button"
          className="image-modal-report"
          onClick={onReport}
          title="Report this image for an objective problem"
        >
          Report
        </button>
      )}
    </div>,
    document.body,
  )
}
