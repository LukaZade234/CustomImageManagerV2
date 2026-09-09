import { forwardRef } from 'react'
import { cx } from '../../utils/cx'

const Input = forwardRef(function Input({ invalid, className, ...rest }, ref) {
  return (
    <input
      ref={ref}
      {...rest}
      aria-invalid={invalid || undefined}
      className={cx('ui-input', invalid && 'is-invalid', className)}
    />
  )
})

export default Input
