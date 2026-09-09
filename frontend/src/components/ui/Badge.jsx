import { cx } from '../../utils/cx'

/** Small inline count or status label. `tone` maps onto the status tokens. */
export default function Badge({ tone = 'neutral', className, children, ...rest }) {
  return (
    <span {...rest} className={cx('ui-badge', `ui-badge--${tone}`, className)}>
      {children}
    </span>
  )
}
