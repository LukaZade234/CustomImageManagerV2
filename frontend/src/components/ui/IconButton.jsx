import Button from './Button'

/**
 * A square or circular button holding only an icon. `label` is required — an
 * icon-only control with no accessible name is invisible to screen readers.
 */
export default function IconButton({ label, round = true, variant = 'ghost', ...rest }) {
  return (
    <Button
      {...rest}
      variant={variant}
      iconOnly
      round={round}
      aria-label={label}
      title={rest.title ?? label}
    />
  )
}
