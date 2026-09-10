/**
 * Drag-to-scroll for the "just added" strip.
 *
 * The whole difficulty is telling a drag from a click. The strip is made of
 * links, so getting it wrong either navigates every time someone pulls the
 * strip, or stops the links working at all. Both failures are silent.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { useDragScroll } from './useDragScroll'

function Strip({ onClick }) {
  const drag = useDragScroll()
  return (
    <ul data-testid="strip" {...drag}>
      <li>
        {/* Stands in for the <Link> the real strip is made of. */}
        <button type="button" onClick={onClick} data-testid="item">
          item
        </button>
      </li>
    </ul>
  )
}

const down = (el, x) => fireEvent.pointerDown(el, { pointerType: 'mouse', button: 0, clientX: x })
const move = (el, x) => fireEvent.pointerMove(el, { pointerType: 'mouse', clientX: x })

describe('useDragScroll', () => {
  it('scrolls the strip by however far the pointer moved', () => {
    render(<Strip />)
    const strip = screen.getByTestId('strip')
    strip.scrollLeft = 100

    down(strip, 200)
    move(strip, 140)
    expect(strip.scrollLeft).toBe(160)
  })

  it('ignores movement below the slop, so a wobble is still a click', () => {
    render(<Strip />)
    const strip = screen.getByTestId('strip')
    strip.scrollLeft = 50

    down(strip, 200)
    move(strip, 197)
    expect(strip.scrollLeft).toBe(50)
  })

  it('lets a plain click through to the link', () => {
    const onClick = vi.fn()
    render(<Strip onClick={onClick} />)
    const strip = screen.getByTestId('strip')

    down(strip, 200)
    fireEvent.pointerUp(strip)
    fireEvent.click(screen.getByTestId('item'))

    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('swallows the click that a drag produces', () => {
    const onClick = vi.fn()
    render(<Strip onClick={onClick} />)
    const strip = screen.getByTestId('strip')

    down(strip, 200)
    move(strip, 120)
    fireEvent.pointerUp(strip)
    fireEvent.click(screen.getByTestId('item'))

    expect(onClick).not.toHaveBeenCalled()
  })

  it('swallows only that one click, not the next real one', () => {
    const onClick = vi.fn()
    render(<Strip onClick={onClick} />)
    const strip = screen.getByTestId('strip')

    down(strip, 200)
    move(strip, 120)
    fireEvent.pointerUp(strip)
    fireEvent.click(screen.getByTestId('item'))
    fireEvent.click(screen.getByTestId('item'))

    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('marks the strip while dragging, for the grabbing cursor', () => {
    render(<Strip />)
    const strip = screen.getByTestId('strip')

    down(strip, 200)
    expect(strip).not.toHaveClass('is-dragging')
    move(strip, 120)
    expect(strip).toHaveClass('is-dragging')
    fireEvent.pointerUp(strip)
    expect(strip).not.toHaveClass('is-dragging')
  })

  it('leaves touch alone, because a finger already pans a scroll container', () => {
    render(<Strip />)
    const strip = screen.getByTestId('strip')
    strip.scrollLeft = 30

    fireEvent.pointerDown(strip, { pointerType: 'touch', button: 0, clientX: 200 })
    fireEvent.pointerMove(strip, { pointerType: 'touch', clientX: 100 })
    expect(strip.scrollLeft).toBe(30)
  })

  it('gives up cleanly when the pointer leaves the strip', () => {
    render(<Strip />)
    const strip = screen.getByTestId('strip')

    down(strip, 200)
    move(strip, 120)
    fireEvent.pointerLeave(strip)
    expect(strip).not.toHaveClass('is-dragging')

    // A move after leaving must not keep scrolling it.
    const at = strip.scrollLeft
    move(strip, 40)
    expect(strip.scrollLeft).toBe(at)
  })
})
