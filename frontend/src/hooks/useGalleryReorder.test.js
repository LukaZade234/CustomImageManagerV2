/**
 * The reorder gesture state machine.
 *
 * This replaced two implementations — HTML5 drag for mouse, hand-rolled touch
 * listeners for everything else — so the cases worth pinning are the ones where
 * those two used to differ, and the ones that were previously impossible to
 * test at all: a scroll must not become a drag, and abandoning a gesture must
 * not strand a capture.
 */
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useGalleryReorder } from './useGalleryReorder'

const ITEMS = ['a', 'b', 'c', 'd']

let captured
let released

function element() {
  return {
    setPointerCapture: vi.fn((id) => {
      captured = id
    }),
    releasePointerCapture: vi.fn((id) => {
      released = id
    }),
  }
}

const down = (_index, { pointerType = 'mouse', x = 0, y = 0, pointerId = 1 } = {}) => ({
  pointerId,
  pointerType,
  button: 0,
  clientX: x,
  clientY: y,
  currentTarget: element(),
})

const move = (x, y, pointerId = 1) => ({
  pointerId,
  clientX: x,
  clientY: y,
  preventDefault: vi.fn(),
})

function setup(onReorder = vi.fn(), enabled = true) {
  const view = renderHook(
    ({ on }) =>
      useGalleryReorder({
        items: ITEMS,
        enabled: on,
        indicesFor: (i) => [i],
        onReorder,
      }),
    { initialProps: { on: enabled } },
  )
  return { view, onReorder }
}

beforeEach(() => {
  captured = null
  released = null
  vi.useFakeTimers()
  // The hook resolves a drop target by hit-testing the point under the pointer.
  document.elementFromPoint = vi.fn(() => ({
    closest: () => ({ getAttribute: () => '2' }),
  }))
})

afterEach(() => {
  vi.useRealTimers()
})

describe('mouse', () => {
  it('does not start dragging until the pointer has moved', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    expect(view.result.current.isDragging).toBe(false)
  })

  it('starts dragging once past the slop', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    expect(view.result.current.isDragging).toBe(true)
    expect(captured).toBe(1)
  })

  it('a click without movement reorders nothing', () => {
    const { view, onReorder } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerUp())
    expect(onReorder).not.toHaveBeenCalled()
    expect(view.result.current.consumeClickAfterDrag()).toBe(false)
  })

  it('releasing commits the new order', () => {
    const { view, onReorder } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    act(() => view.result.current.itemProps(0).onPointerUp())
    expect(onReorder).toHaveBeenCalledWith(['b', 'a', 'c', 'd'])
    expect(released).toBe(1)
  })

  it('cancelling discards it', () => {
    const { view, onReorder } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    act(() => view.result.current.itemProps(0).onPointerCancel())
    expect(onReorder).not.toHaveBeenCalled()
    expect(view.result.current.isDragging).toBe(false)
  })

  it('ignores a right-click', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown({ ...down(0), button: 2 }))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    expect(view.result.current.isDragging).toBe(false)
  })
})

describe('touch', () => {
  it('needs a long press before it drags', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0, { pointerType: 'touch' })))
    expect(view.result.current.isDragging).toBe(false)
    act(() => vi.advanceTimersByTime(500))
    expect(view.result.current.isDragging).toBe(true)
  })

  it('treats movement before the long press as a scroll and gives up', () => {
    // The whole reason a long press exists: a finger moving across a gallery is
    // ordinarily scrolling it.
    const { view, onReorder } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0, { pointerType: 'touch' })))
    act(() => view.result.current.itemProps(0).onPointerMove(move(0, 90)))
    act(() => vi.advanceTimersByTime(500))
    expect(view.result.current.isDragging).toBe(false)
    expect(onReorder).not.toHaveBeenCalled()
  })

  it('tolerates a small wobble during the press', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0, { pointerType: 'touch' })))
    act(() => view.result.current.itemProps(0).onPointerMove(move(3, 3)))
    act(() => vi.advanceTimersByTime(500))
    expect(view.result.current.isDragging).toBe(true)
  })
})

describe('drop target', () => {
  it('follows the item under the pointer', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    expect(view.result.current.dropTargetIndex).toBe(2)
  })

  it('clears when the gesture ends', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    act(() => view.result.current.itemProps(0).onPointerUp())
    expect(view.result.current.dropTargetIndex).toBeNull()
  })
})

describe('teardown', () => {
  it('leaving reorder mode mid-drag releases the capture', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    expect(view.result.current.isDragging).toBe(true)

    act(() => view.rerender({ on: false }))
    expect(view.result.current.isDragging).toBe(false)
    expect(released).toBe(1)
  })

  it('offers no handlers at all when reorder mode is off', () => {
    const { view } = setup(vi.fn(), false)
    expect(view.result.current.itemProps(0)).toEqual({})
  })

  it('blocks the native image menu while reordering', () => {
    // On a phone the browser's own long-press menu appears partway through the
    // press that starts a drag, turning reordering into a race against it.
    const { view } = setup()
    const event = { preventDefault: vi.fn() }
    view.result.current.itemProps(0).onContextMenu(event)
    expect(event.preventDefault).toHaveBeenCalled()
  })

  it('leaves the native image menu alone outside reorder mode', () => {
    const { view } = setup(vi.fn(), false)
    expect(view.result.current.itemProps(0).onContextMenu).toBeUndefined()
  })

  it('swallows exactly one click after a drag', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60)))
    act(() => view.result.current.itemProps(0).onPointerUp())
    expect(view.result.current.consumeClickAfterDrag()).toBe(true)
    expect(view.result.current.consumeClickAfterDrag()).toBe(false)
  })

  it('ignores events from a second pointer', () => {
    const { view } = setup()
    act(() => view.result.current.itemProps(0).onPointerDown(down(0)))
    act(() => view.result.current.itemProps(0).onPointerMove(move(60, 60, 99)))
    expect(view.result.current.isDragging).toBe(false)
  })
})
