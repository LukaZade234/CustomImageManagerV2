import { useState, useRef, useEffect, useMemo } from 'react'

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
  const wrapRef = useRef(null)

  const filtered = useMemo(() => {
    const q = value.trim().toLowerCase()
    const list = q
      ? suggestions.filter((s) => s.toLowerCase().includes(q))
      : suggestions
    return list.slice(0, 25)
  }, [value, suggestions])

  useEffect(() => {
    const close = (e) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  const showList = open && !disabled && filtered.length > 0

  const pick = (s) => {
    onChange({ target: { value: s } })
    setOpen(false)
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
        }}
        onFocus={() => setOpen(true)}
        placeholder={placeholder}
        disabled={disabled}
        autoComplete="off"
        aria-autocomplete="list"
        aria-expanded={showList}
        role="combobox"
      />
      {showList && (
        <div className="autocomplete-items" role="listbox" aria-label="Series suggestions">
          {filtered.map((s) => (
            <div
              key={s}
              className="autocomplete-item"
              role="option"
              onMouseDown={(e) => {
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
