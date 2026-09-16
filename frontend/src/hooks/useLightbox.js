import { useCallback, useEffect, useRef, useState } from 'react'
import { ratioOf } from '../utils/galleryRatios'

/**
 * The full-screen image viewer and the gallery's measured ratios.
 *
 * Split out of `CharacterPage`. The ratio measurement is the reason this is not
 * a trivial open/close: `onLoad` fires once per image in its own tick, so a
 * 256-image gallery meant 256 full re-renders of the grid as it filled in.
 * Coalescing a frame's worth of measurements into one state update makes the
 * fill cost one render per frame instead.
 */
export function useLightbox({ imageCount, canOpen = true }) {
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)
  const [ratios, setRatios] = useState({})

  const pendingRatiosRef = useRef({})
  const ratioFrameRef = useRef(0)
  useEffect(() => () => cancelAnimationFrame(ratioFrameRef.current), [])

  const noteRatio = useCallback((imageId, element) => {
    const ratio = ratioOf(element)
    if (ratio === null) return
    pendingRatiosRef.current[imageId] = ratio
    if (ratioFrameRef.current) return
    ratioFrameRef.current = requestAnimationFrame(() => {
      ratioFrameRef.current = 0
      const pending = pendingRatiosRef.current
      pendingRatiosRef.current = {}
      setRatios((prev) => {
        let changed = false
        const next = { ...prev }
        for (const [id, measured] of Object.entries(pending)) {
          if (next[id] !== measured) {
            next[id] = measured
            changed = true
          }
        }
        return changed ? next : prev
      })
    })
  }, [])

  // The viewer only opens from browse; in any other mode a click on an image is
  // a selection, not an invitation to look at it.
  const openAt = useCallback(
    (at) => {
      if (!canOpen) return
      setIndex(at)
      setOpen(true)
    },
    [canOpen],
  )

  const close = useCallback(() => setOpen(false), [])
  const prev = useCallback(() => setIndex((i) => Math.max(0, i - 1)), [])
  const next = useCallback(
    () => setIndex((i) => Math.min(Math.max(0, imageCount - 1), i + 1)),
    [imageCount],
  )

  return {
    open,
    index,
    ratios,
    noteRatio,
    openAt,
    close,
    prev,
    next,
    setIndex,
  }
}
