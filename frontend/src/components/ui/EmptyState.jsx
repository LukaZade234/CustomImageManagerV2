import { cx } from '../../utils/cx'

/** Explains why a region is empty and offers the way out of it. */
export default function EmptyState({ title, description, action, className }) {
  return (
    <div className={cx('ui-empty', className)}>
      <p className="ui-empty__title">{title}</p>
      {description && <p className="ui-empty__desc">{description}</p>}
      {action && <div className="ui-empty__action">{action}</div>}
    </div>
  )
}
