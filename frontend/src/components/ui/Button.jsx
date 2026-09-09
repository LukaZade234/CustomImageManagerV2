import { cx } from '../../utils/cx'

/**
 * The one button in the system.
 *
 * Replaces eight hand-rolled styles that shared no base, plus the
 * `style={{ padding: '6px 12px', fontSize: '0.9em' }}` override that was
 * repeated fifteen times in CharacterPage alone. If a caller needs a size that
 * is not `sm` or `md`, that is a signal the scale is wrong — fix it here rather
 * than passing an inline style.
 */
export default function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  iconOnly = false,
  round = false,
  className,
  children,
  disabled,
  ...rest
}) {
  return (
    <button
      type="button"
      {...rest}
      className={cx(
        'ui-btn',
        `ui-btn--${variant}`,
        `ui-btn--${size}`,
        iconOnly && 'ui-btn--icon',
        round && 'ui-btn--round',
        loading && 'is-loading',
        className,
      )}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
    >
      {loading && <span className="ui-btn__spinner" aria-hidden="true" />}
      {children}
    </button>
  )
}
