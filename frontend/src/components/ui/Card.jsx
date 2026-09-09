import { cx } from '../../utils/cx'

/**
 * The single surface recipe. The old stylesheet had four of these with
 * different padding, radius and shadow values for the same job, which is most
 * of why the site read as inconsistent.
 */
export default function Card({ as: Tag = 'div', padding = 'md', className, children, ...rest }) {
  return (
    <Tag {...rest} className={cx('ui-card', `ui-card--pad-${padding}`, className)}>
      {children}
    </Tag>
  )
}
