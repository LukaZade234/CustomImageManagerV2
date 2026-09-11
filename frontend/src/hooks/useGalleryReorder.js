import { useCallback, useEffect, useRef, useState } from 'react'
import { moveGroupInArray, ordersEqual } from '../utils/reorderArray'

/**
 * Drag-to-reorder for the custom image gallery.
 *
 * This replaces two separate implementations — HTML5 drag-and-drop for mouse and
 * a hand-rolled touchstart/touchmove/touchend stack for touch — with one built
 * on pointer events.
 *
 * Two things fall out of that, and the second matters more than the first.
 *
 * `setPointerCapture` sends every subsequent move and release to the element
 * that was grabbed, so the handlers can be ordinary React props on the item and
 * the browser releases them on its own. The old code kept six refs alive purely
 * to hold cleanup callbacks, and wrote the same three removeEventListener calls
 * out in four places, because a long press can be abandoned at three different
 * points.
 *
 * More importantly, reordering no longer travels over HTML5 drag-and-drop — so
 * that channel now means only "something arrived from outside". Every handler
 * used to sniff `dataTransfer` to work out whether a drag was an internal
 * reorder, a dropped file, or an image dragged in from a web page. None of that
 * disambiguation is needed once the three stop sharing a wire.
 *
 * Touch still needs a long press. A finger moving across the gallery is
 * ordinarily a scroll, and the only way to know otherwise is that the user held
 * still first. During the delay nothing is captured and nothing is prevented, so
 * a scroll behaves normally and simply cancels the pending drag. A mouse has no
 * such ambiguity and starts as soon as the pointer moves past the slop.
 */

/** Held this long before a touch counts as a drag rather than a scroll. */
const LONG_PRESS_MS = 450
/** Movement below this is a tap, or the hand shake before a long press. */
const SLOP_PX = 14

/** Auto-scroll when dragging near the top or bottom of the viewport. */
const EDGE_BAND_PX = 100
const EDGE_STEP_MIN = 5
const EDGE_STEP_MAX = 28

function slotIndexAt(clientX, clientY) {
  const el = document.elementFromPoint(clientX, clientY)
  const slot = el?.closest?.('[data-reorder-slot]')
  if (!slot) return null
  const index = Number.parseInt(slot.getAttribute('data-reorder-slot') ?? '', 10)
  return Number.isFinite(index) ? index : null
}

/**
 * @param {object} options
 * @param {string[]} options.items       current order
 * @param {boolean} options.enabled      whether reorder mode is on
 * @param {(index:number) => number[]} options.indicesFor  which items a grab moves
 * @param {(next:string[]) => void} options.onReorder      apply a new order
 */
export function useGalleryReorder({ items, enabled, indicesFor, onReorder }) {
  const [dragIndices, setDragIndices] = useState(null)
  const [dropTargetIndex, setDropTargetIndex] = useState(null)
  const [announcement, setAnnouncement] = useState('')

  // One ref for the whole gesture, rather than one per thing being tracked.
  const gesture = useRef(null)
  // Set when a drag ends, so the synthetic click that follows does not toggle
  // the selection of whatever the pointer happened to be over.
  const swallowNextClick = useRef(false)

  const endGesture = useCallback(() => {
    const active = gesture.current
    gesture.current = null
    if (!active) return null
    clearTimeout(active.timer)
    if (active.dragging) {
      document.body.classList.remove('reorder-touch-dragging')
      window.removeEventListener('touchmove', active.blockScroll)
      try {
        active.element?.releasePointerCapture?.(active.pointerId)
      } catch {
        // Already released, or the element is gone. Nothing to do.
      }
    }
    return active
  }, [])

  const beginDrag = useCallback(
    (active) => {
      active.dragging = true
      const indices = indicesFor(active.index)
      setDragIndices(indices)
      setDropTargetIndex(active.index)
      active.dropIndex = active.index

      try {
        active.element.setPointerCapture(active.pointerId)
      } catch {
        // Safari occasionally refuses if the pointer already went away; the
        // gesture simply ends at the next up or cancel.
      }
      if (active.pointerType !== 'mouse') {
        // Capture alone does not stop the page scrolling under a finger.
        document.body.classList.add('reorder-touch-dragging')
        window.addEventListener('touchmove', active.blockScroll, { passive: false })
      }
    },
    [indicesFor],
  )

  const onPointerDown = useCallback(
    (event, index) => {
      if (!enabled) return
      if (event.pointerType === 'mouse' && event.button !== 0) return
      endGesture()

      const active = {
        pointerId: event.pointerId,
        pointerType: event.pointerType,
        index,
        startX: event.clientX,
        startY: event.clientY,
        pointerY: event.clientY,
        element: event.currentTarget,
        dragging: false,
        dropIndex: null,
        timer: 0,
        blockScroll: (e) => e.preventDefault(),
      }
      gesture.current = active

      if (event.pointerType !== 'mouse') {
        active.timer = setTimeout(() => {
          if (gesture.current === active && !active.dragging) beginDrag(active)
        }, LONG_PRESS_MS)
      }
    },
    [enabled, endGesture, beginDrag],
  )

  const onPointerMove = useCallback(
    (event) => {
      const active = gesture.current
      if (!active || event.pointerId !== active.pointerId) return
      active.pointerY = event.clientY

      if (!active.dragging) {
        const dx = event.clientX - active.startX
        const dy = event.clientY - active.startY
        if (dx * dx + dy * dy <= SLOP_PX * SLOP_PX) return
        // A mouse that has moved is dragging. A finger that has moved before the
        // long press elapsed is scrolling, so abandon the gesture entirely.
        if (active.pointerType !== 'mouse') {
          endGesture()
          return
        }
        beginDrag(active)
        // Falls through: the move that starts a drag should also settle where
        // it would drop, or a quick grab-and-release lands back at the origin.
      }

      event.preventDefault()
      const over = slotIndexAt(event.clientX, event.clientY)
      if (over != null && over !== active.dropIndex) {
        active.dropIndex = over
        setDropTargetIndex(over)
      }
    },
    [beginDrag, endGesture],
  )

  const finish = useCallback(
    (commit) => {
      const active = endGesture()
      setDragIndices(null)
      setDropTargetIndex(null)
      if (!active?.dragging) return

      swallowNextClick.current = true
      if (!commit || active.dropIndex == null) return

      const indices = indicesFor(active.index)
      if (!indices.length) return
      const next = moveGroupInArray(items, indices, active.dropIndex)
      if (!ordersEqual(next, items)) onReorder(next)
    },
    [endGesture, indicesFor, items, onReorder],
  )

  const onPointerUp = useCallback(() => finish(true), [finish])
  const onPointerCancel = useCallback(() => finish(false), [finish])

  /** True once per drag, so the click that follows can be ignored. */
  const consumeClickAfterDrag = useCallback(() => {
    if (!swallowNextClick.current) return false
    swallowNextClick.current = false
    return true
  }, [])

  // Leaving reorder mode mid-gesture must not strand a capture or a listener.
  useEffect(() => {
    if (enabled) return
    endGesture()
    setDragIndices(null)
    setDropTargetIndex(null)
  }, [enabled, endGesture])

  useEffect(() => endGesture, [endGesture])

  /**
   * Keep scrolling while the pointer rests in the top or bottom band.
   *
   * A frame loop rather than reacting to movement: the pointer can sit still at
   * the edge of a long gallery, and the scroll should continue.
   */
  useEffect(() => {
    if (!dragIndices) return undefined
    let rafId = 0
    const tick = () => {
      const y = gesture.current?.pointerY
      if (y != null) {
        const height = window.innerHeight
        const past =
          y < EDGE_BAND_PX
            ? y - EDGE_BAND_PX
            : y > height - EDGE_BAND_PX
              ? y - (height - EDGE_BAND_PX)
              : 0
        if (past !== 0) {
          const magnitude = Math.min(
            EDGE_STEP_MAX,
            Math.max(EDGE_STEP_MIN, 4 + Math.abs(past) * 0.22),
          )
          window.scrollBy(0, Math.round(Math.sign(past) * magnitude))
        }
      }
      rafId = requestAnimationFrame(tick)
    }
    rafId = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(rafId)
  }, [dragIndices])

  /**
   * Move an item with the arrow keys.
   *
   * Reordering was pointer-only: `itemProps` carried nothing but pointer
   * handlers, so a keyboard user could add images, remove them and copy a
   * command, but could not control the order the command actually emits — which
   * is the product's whole output. The help panel cheerfully told them to drag.
   *
   * The same `moveGroupInArray` path the pointer drag uses, so a grouped
   * selection moves together here too. `moveGroupInArray` inserts *before* the
   * target index, so moving right has to aim one past the neighbour to land
   * after it.
   */
  const onItemKeyDown = useCallback(
    (event, index) => {
      if (!enabled) return
      const back = event.key === 'ArrowLeft' || event.key === 'ArrowUp'
      const forward = event.key === 'ArrowRight' || event.key === 'ArrowDown'
      if (!back && !forward) return

      const indices = indicesFor(index)
      if (!indices.length) return
      const lowest = Math.min(...indices)
      const highest = Math.max(...indices)
      const target = back ? lowest - 1 : highest + 2
      if (back ? lowest <= 0 : highest >= items.length - 1) return

      event.preventDefault()
      const next = moveGroupInArray(items, indices, target)
      if (ordersEqual(next, items)) return
      onReorder(next)

      // Focus follows the item to its new home, or the arrow keys walk away
      // from the thing being moved after one press.
      const landing = back ? lowest - 1 : lowest + 1
      requestAnimationFrame(() => {
        document.querySelector(`[data-reorder-slot="${landing}"]`)?.focus?.()
      })
      setAnnouncement(
        `Moved to position ${landing + 1} of ${items.length}` +
          (indices.length > 1 ? `, with ${indices.length - 1} more` : ''),
      )
    },
    [enabled, indicesFor, items, onReorder],
  )

  /** Spread onto each gallery item. */
  const itemProps = useCallback(
    (index) =>
      enabled
        ? {
            onPointerDown: (e) => onPointerDown(e, index),
            onPointerMove,
            onPointerUp,
            onPointerCancel,
            // Android fires contextmenu partway through a long press, which
            // opens the browser's own image menu on top of the drag. Outside
            // reorder mode that menu is useful, so this is scoped to the mode
            // rather than applied to the gallery generally.
            onContextMenu: (e) => e.preventDefault(),
            onKeyDown: (e) => onItemKeyDown(e, index),
          }
        : {},
    [enabled, onPointerDown, onPointerMove, onPointerUp, onPointerCancel, onItemKeyDown],
  )

  return {
    dragIndices,
    dropTargetIndex,
    isDragging: dragIndices != null,
    itemProps,
    consumeClickAfterDrag,
    /** For a polite live region: a pointer drag is visible, a key press is not. */
    announcement,
  }
}
