import { useEffect, useState } from 'react'

/**
 * Whether a media query currently matches, as state.
 *
 * CSS handles almost everything responsive here, and should: a rule in a media
 * query cannot get out of step with the layout it describes. This exists for
 * the two places where the *markup* differs rather than its appearance — the
 * navbar folds its links behind a button, and the gallery lays out in uniform
 * columns instead of uniform rows — because both need different elements, not
 * different styling on the same ones.
 *
 * Read synchronously on the first render, so nothing flashes in the wrong shape
 * before an effect corrects it. `matchMedia` is missing in some test
 * environments; absent means "does not match", which leaves the wide layout as
 * the default everywhere it is unavailable.
 */
export function useMediaQuery(query) {
  const [matches, setMatches] = useState(() => window.matchMedia?.(query).matches ?? false)

  useEffect(() => {
    const list = window.matchMedia?.(query)
    if (!list) return undefined
    // Re-read on subscribe: the viewport can change between the first render
    // and this effect, and the listener only fires on changes after it.
    setMatches(list.matches)
    const onChange = (event) => setMatches(event.matches)
    list.addEventListener('change', onChange)
    return () => list.removeEventListener('change', onChange)
  }, [query])

  return matches
}
