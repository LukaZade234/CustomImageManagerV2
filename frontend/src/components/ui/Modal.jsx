import { createPortal } from 'react-dom'
import { cx } from '../../utils/cx'
import { useDialog } from './useDialog'

/**
 * Card-style dialog on a scrim. Rendered through a portal so a dialog opened
 * from deep in the tree is not clipped by an ancestor's overflow or stacking
 * context — the previous dialogs all rendered inline and relied on luck.
 */
export default function Modal({
  onClose,
  title,
  titleId = 'ui-modal-title',
  size = 'md',
  className,
  children,
  footer,
}) {
  const { dialogRef, onKeyDown, onBackdropClick } = useDialog({ onClose })

  return createPortal(
    <div
      className="ui-modal-backdrop"
      // biome-ignore lint/a11y/noStaticElementInteractions: the backdrop is a
      // convenience dismissal; Escape and the close button are the real controls.
      onClick={onBackdropClick}
      role="presentation"
    >
      <div
        ref={dialogRef}
        className={cx('ui-modal', `ui-modal--${size}`, className)}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? titleId : undefined}
        tabIndex={-1}
        onKeyDown={onKeyDown}
      >
        {title && (
          <header className="ui-modal__header">
            <h2 className="ui-modal__title" id={titleId}>
              {title}
            </h2>
          </header>
        )}
        <div className="ui-modal__body">{children}</div>
        {footer && <footer className="ui-modal__footer">{footer}</footer>}
      </div>
    </div>,
    document.body,
  )
}
