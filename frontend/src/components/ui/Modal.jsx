import { createPortal } from 'react-dom'
import { cx } from '../../utils/cx'
import IconButton from './IconButton'
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
    // Dismissing by clicking the backdrop is mouse convenience layered on top of
    // the real controls: the dialog traps focus, Escape closes it, and it has a
    // visible close button. Nothing here is denied to a keyboard user.
    //
    // That last claim was written before the button existed. On a phone the
    // backdrop is a 16px band nobody can reliably hit, Escape needs a keyboard,
    // and a long list scrolled the title away — so a dialog could be opened with
    // no visible way out of it at all.
    // biome-ignore lint/a11y/noStaticElementInteractions: backdrop dismissal, see above
    <div className="ui-modal-backdrop" role="presentation" onClick={onBackdropClick}>
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
            <IconButton className="ui-modal__close" label="Close" onClick={onClose}>
              <svg
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </IconButton>
          </header>
        )}
        <div className="ui-modal__body">{children}</div>
        {footer && <footer className="ui-modal__footer">{footer}</footer>}
      </div>
    </div>,
    document.body,
  )
}
