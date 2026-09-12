import { useEffect, useRef } from 'react'

/**
 * The sort control on a narrow screen: an arrow that opens a list under it.
 *
 * A native `<select>` is the better control almost everywhere — it is what the
 * rest of the app uses, and on a phone it hands the job to the platform. But
 * the platform answers with a sheet in the middle of the screen, unattached to
 * the thing that opened it, and that is not what this bar wants: the list
 * belongs under the arrow, over the search field it is borrowing space from.
 *
 * So this is the one hand-built menu in the app, and it owes the native control
 * everything the native control gave away: arrow keys, Escape, a click outside,
 * focus landing on the current choice and returning to the button afterwards.
 * They are written out here rather than assumed.
 */
export function SortMenu({ options, value, open, onOpenChange, onChange }) {
  const wrap = useRef(null)
  const toggle = useRef(null)
  const current = options.find((option) => option.value === value)

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

  return (
    <div className={`sort-menu${open ? ' is-open' : ''}`} ref={wrap}>
      <button
        ref={toggle}
        onKeyDown={onKeyDown}
        type="button"
        className="ui-btn ui-btn--secondary ui-btn--md sort-menu__toggle"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Sort: ${current?.label ?? ''}. Change.`}
        onClick={() => onOpenChange(!open)}
      >
        {/* The label appears only while open: folded, this is an arrow, and the
            answer it would show is the one already on screen in the results. */}
        {open && <span className="sort-menu__current">{current?.label}</span>}
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
          aria-label="Sort results"
          onKeyDown={onKeyDown}
        >
          {options.map((option) => (
            <button
              key={option.value}
              type="button"
              role="menuitemradio"
              aria-checked={option.value === value}
              className="sort-menu__item"
              onClick={() => {
                onChange(option.value)
                close(true)
              }}
            >
              <span className="sort-menu__tick" aria-hidden="true">
                {option.value === value ? '✓' : ''}
              </span>
              {option.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
