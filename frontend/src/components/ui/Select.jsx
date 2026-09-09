import { forwardRef } from 'react'
import { cx } from '../../utils/cx'

/**
 * A native <select>. The old sort menu was a div-based listbox with a
 * document-level click-outside listener, no arrow-key navigation and no
 * Escape — a native control does all of that correctly and for free.
 */
const Select = forwardRef(function Select({ className, children, ...rest }, ref) {
  return (
    <select ref={ref} {...rest} className={cx('ui-select', className)}>
      {children}
    </select>
  )
})

export default Select
