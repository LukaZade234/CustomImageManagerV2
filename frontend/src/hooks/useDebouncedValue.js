import { useEffect, useState } from 'react'

/**
 * A value that trails the one passed in by `delay` milliseconds.
 *
 * react-query has no debounce of its own, and keying a query on every keystroke
 * would fire a request per character. Debouncing the input and keying on the
 * settled value keeps a fast typist to one request while still letting the
 * cache serve a query that was typed before.
 */
export function useDebouncedValue(value, delay = 250) {
  const [debounced, setDebounced] = useState(value)
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])
  return debounced
}
