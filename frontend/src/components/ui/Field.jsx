import { useId } from 'react'
import { cx } from '../../utils/cx'

/**
 * Label + control + optional hint or error, wired together by id so the label
 * actually labels something and the hint is announced with it.
 */
export default function Field({ label, hint, error, children, className, htmlFor }) {
  const generated = useId()
  const id = htmlFor ?? generated
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined

  return (
    <div className={cx('ui-field', className)}>
      <label className="ui-field__label" htmlFor={id}>
        {label}
      </label>
      {typeof children === 'function' ? children({ id, describedBy }) : children}
      {hint && !error && (
        <p className="ui-field__hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      {error && (
        <p className="ui-field__error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  )
}
