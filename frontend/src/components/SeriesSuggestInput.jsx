import { useEffect, useId, useMemo, useRef, useState } from 'react'

/**
 * A text input with a filtered list of existing series.
 *
 * Follows the ARIA combobox-with-listbox pattern, which matters here because the
 * list used to be selectable only with `onMouseDown`: there was no way to choose
 * a suggestion from the keyboard at all, and the options carried `role="option"`
 * while being unreachable.
 *
 * In that pattern focus never leaves the input. The arrow keys move a *virtual*
 * cursor and `aria-activedescendant` tells the screen reader which option it is
 * on, so the options themselves are deliberately not tabbable — making them
 * focusable would break the pattern rather than improve it.
 */
export default function SeriesSuggestInput({
  id,
  value,
  onChange,
  suggestions = [],
  placeholder,
  disabled,
  className = 'modern-input',
  wrapClassName = 'series-suggest-wrap',
  style,
}) {
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(-1)
  const wrapRef = useRef(null)
  const listId = useId()

  const filtered = useMemo(() => {
    const q = value.trim().toLowerCase()
    const list = q ? suggestions.filter((s) => s.toLowerCase().includes(q)) : suggestions
    return list.slice(0, 25)
  }, [value, suggestions])

  useEffect(() => {
    const close = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  // Whenever the list itself changes -- typing, or a new suggestions prop -- the
  // cursor goes back to nothing rather than pointing at whatever has since moved
  // into that position. `filtered` is the trigger, not an input: the body does
  // not read it, so Biome would drop it and make this mount-only.
  // biome-ignore lint/correctness/useExhaustiveDependencies: trigger, not an input
  useEffect(() => {
    setActiveIndex(-1)
  }, [filtered])

  const showList = open && !disabled && filtered.length > 0
  const optionId = (index) => `${listId}-option-${index}`

  const pick = (s) => {
    onChange({ target: { value: s } })
    setOpen(false)
    setActiveIndex(-1)
  }

  const onKeyDown = (e) => {
    if (e.key === 'Escape') {
      setOpen(false)
      setActiveIndex(-1)
      return
    }
    if (!showList) {
      // Arrow Down opens the list without needing a keystroke that edits the text.
      if (e.key === 'ArrowDown' && !disabled && filtered.length > 0) {
        e.preventDefault()
        setOpen(true)
        setActiveIndex(0)
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setActiveIndex((i) => (i + 1) % filtered.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setActiveIndex((i) => (i <= 0 ? filtered.length - 1 : i - 1))
    } else if (e.key === 'Enter' && activeIndex >= 0) {
      // Only swallow Enter when it is actually choosing something, so the key
      // still submits the surrounding form the rest of the time.
      e.preventDefault()
      pick(filtered[activeIndex])
    } else if (e.key === 'Home' && activeIndex >= 0) {
      e.preventDefault()
      setActiveIndex(0)
    } else if (e.key === 'End' && activeIndex >= 0) {
      e.preventDefault()
      setActiveIndex(filtered.length - 1)
    }
  }

  return (
    <div className={wrapClassName} ref={wrapRef} style={style}>
      <input
        id={id}
        type="text"
        className={className}
        value={value}
        onChange={(e) => {
          onChange(e)
          setOpen(true)
          setActiveIndex(-1)
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={showList}
        aria-controls={listId}
        aria-activedescendant={showList && activeIndex >= 0 ? optionId(activeIndex) : undefined}
      />
      {showList && (
        <div
          className="autocomplete-items"
          role="listbox"
          id={listId}
          aria-label="Series suggestions"
        >
          {filtered.map((s, index) => (
            // Focus stays on the input in the combobox pattern; aria-activedescendant
            // above is what moves. Making an option tabbable would break the pattern
            // rather than help.
            // biome-ignore lint/a11y/useFocusableInteractive: virtual cursor, see above
            <div
              key={s}
              id={optionId(index)}
              className={`autocomplete-item${index === activeIndex ? ' is-active' : ''}`}
              role="option"
              aria-selected={index === activeIndex}
              onMouseEnter={() => setActiveIndex(index)}
              onMouseDown={(e) => {
                // mousedown, not click: the input's blur would close the list first.
                e.preventDefault()
                pick(s)
              }}
            >
              {s}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
