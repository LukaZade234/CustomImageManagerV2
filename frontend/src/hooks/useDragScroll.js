import { useCallback, useRef } from 'react'

/**
 * Drag a horizontally scrolling strip sideways with the mouse.
 *
 * A wheel is a poor fit for a horizontal strip — a plain mouse only scrolls
 * vertically, so without this the only way through is a trackpad gesture or the
 * scrollbar. Grabbing the strip and pulling is what people try first.
 *
 * Touch is deliberately left alone: a finger already pans a scroll container,
 * and intercepting it would replace something that works with something worse.
 * Pointer capture is not used either, because capturing would swallow the
 * `click` that follows a plain tap and break every link inside the strip.
 *
 * Instead a drag is recognised only once the pointer has travelled past a small
 * threshold, and only then is the following click suppressed — so a click still
 * navigates and a drag does not.
 */

/** Past this much movement it is a drag, not a click that wobbled. */
const SLOP_PX = 6

export function useDragScroll() {
  const state = useRef(null)

  const onPointerDown = useCallback((event) => {
    if (event.pointerType !== 'mouse' || event.button !== 0) return
    state.current = {
      element: event.currentTarget,
      startX: event.clientX,
      startScroll: event.currentTarget.scrollLeft,
      dragging: false,
    }
  }, [])

  const onPointerMove = useCallback((event) => {
    const active = state.current
    if (!active) return
    const dx = event.clientX - active.startX
    if (!active.dragging) {
      if (Math.abs(dx) < SLOP_PX) return
      active.dragging = true
      active.element.classList.add('is-dragging')
    }
    // Without this the browser's own text/image drag starts mid-pull.
    event.preventDefault()
    active.element.scrollLeft = active.startScroll - dx
  }, [])

  const end = useCallback(() => {
    const active = state.current
    state.current = null
    if (!active) return
    active.element.classList.remove('is-dragging')
    if (active.dragging) {
      // Swallow exactly one click: the one this drag is about to produce on
      // whichever link the pointer happens to be resting over.
      const swallow = (e) => {
        e.preventDefault()
        e.stopPropagation()
      }
      active.element.addEventListener('click', swallow, { capture: true, once: true })
      // If no click follows -- the pointer left the strip -- do not leave the
      // listener armed to eat someone's next legitimate click.
      setTimeout(() => active.element.removeEventListener('click', swallow, { capture: true }), 0)
    }
  }, [])

  return {
    onPointerDown,
    onPointerMove,
    onPointerUp: end,
    onPointerLeave: end,
    onPointerCancel: end,
    onDragStart: (e) => e.preventDefault(),
  }
}
