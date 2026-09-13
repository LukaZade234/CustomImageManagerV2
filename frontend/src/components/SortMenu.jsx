import { Fragment, useEffect, useRef } from 'react'

/**
 * The bar's filter control: an arrow that opens a list under it.
 *
 * A native `<select>` is the better control almost everywhere — it is what the
 * rest of the app uses. But the bar wants one panel holding the search field,
 * the sort and the direction, and a select cannot do that; the platform's own
 * picker would also open as a sheet detached from the control that asked for
 * it. So the list belongs under the arrow, over the search field it is
 * borrowing space from.
 *
 * So this is the one hand-built menu in the app, and it owes the native control
 * everything the native control gave away: arrow keys, Escape, a click outside,
 * focus landing on the current choice and returning to the button afterwards.
 * They are written out here rather than assumed.
 *
 * `before` and `after` add further groups around the sort — the search field
 * choice and the sort direction — so the bar has one filter control instead of
 * a switch crammed into the field and a select beside it. The groups read as
 * one panel because they share the surface, the rows and the dismissal.
 */
export function SortMenu({
  options,
  value,
  open,
  onOpenChange,
  onChange,
  summary,
  before = [],
  after = [],
}) {
  const wrap = useRef(null)
  const toggle = useRef(null)
  const current = options.find((option) => option.value === value)
  const grouped = before.length > 0 || after.length > 0

  // A tap anywhere else is a decision not to choose anything.
  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (event) => {
      if (!wrap.current?.contains(event.target)) onOpenChange(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open, onOpenChange])

  // Open on the current choice, so the list starts where you are.
  useEffect(() => {
    if (!open) return
    wrap.current?.querySelector('[aria-checked="true"]')?.focus()
  }, [open])

  const close = (restoreFocus) => {
    onOpenChange(false)
    if (restoreFocus) toggle.current?.focus()
  }

  const onKeyDown = (event) => {
    if (event.key === 'Escape') {
      event.stopPropagation()
      close(true)
      return
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return
    const items = [...(wrap.current?.querySelectorAll('[role="menuitemradio"]') ?? [])]
    if (!items.length) return
    event.preventDefault()
    const at = items.indexOf(document.activeElement)
    const step = event.key === 'ArrowDown' ? 1 : -1
    items[(at + step + items.length) % items.length].focus()
  }

  const item = (option, checked, onChoose) => (
    <button
      key={option.value}
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      className="sort-menu__item"
      onClick={() => {
        onChoose(option.value)
        close(true)
      }}
    >
      <span className="sort-menu__tick" aria-hidden="true">
        {checked ? '✓' : ''}
      </span>
      {option.label}
    </button>
  )

  const groups = [
    ...before,
    { label: grouped ? 'Sort by' : null, options, value, onChange },
    ...after,
  ]

  return (
    <div className={`sort-menu${open ? ' is-open' : ''}`} ref={wrap}>
      <button
        ref={toggle}
        onKeyDown={onKeyDown}
        type="button"
        className="ui-btn ui-btn--secondary ui-btn--md sort-menu__toggle"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={grouped ? 'Filter. Change.' : `Sort: ${current?.label ?? ''}. Change.`}
        onClick={() => onOpenChange(!open)}
      >
        {/* A summary states the current filter on a wide bar; a plain sort menu
            shows its label only while open. Narrowing hides the summary by CSS,
            since an arrow and its answer do not both fit on a phone. */}
        {summary ? (
          <span className="sort-menu__current">{summary}</span>
        ) : (
          open && !grouped && <span className="sort-menu__current">{current?.label}</span>
        )}
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
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
      {open && (
        <div
          className="sort-menu__list"
          role="menu"
          aria-label={grouped ? 'Filter' : 'Sort results'}
          onKeyDown={onKeyDown}
        >
          {groups.map((group, index) => (
            <Fragment key={group.label ?? 'sort'}>
              {index > 0 && <hr className="sort-menu__rule" />}
              {group.label ? (
                <fieldset className="sort-menu__group">
                  <legend className="sort-menu__group-label">{group.label}</legend>
                  {group.options.map((option) =>
                    item(option, option.value === group.value, group.onChange),
                  )}
                </fieldset>
              ) : (
                group.options.map((option) =>
                  item(option, option.value === group.value, group.onChange),
                )
              )}
            </Fragment>
          ))}
        </div>
      )}
    </div>
  )
}
