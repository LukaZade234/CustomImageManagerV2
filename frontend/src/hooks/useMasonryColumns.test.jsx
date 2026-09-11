/**
 * The arithmetic behind the phone gallery's columns.
 *
 * CSS grid lays out columns of equal width and unequal height only if it is
 * told how many 1px row tracks each item occupies, and it cannot derive that
 * from an aspect ratio. So this counts them — which means a wrong number here
 * is a gallery of overlapping or floating images, with nothing in the markup
 * to say so. Hence tests on the numbers themselves.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useMasonryColumns, WIDE_RATIO } from './useMasonryColumns'

const GAP = 8
/** A 400px container gives two 196px columns with an 8px gap between them. */
const WIDTH = 400
const COLUMN = (WIDTH - GAP) / 2

function Harness({ enabled, ratios }) {
  const columns = useMasonryColumns(enabled)
  return (
    <div ref={columns.ref} data-testid="gallery">
      {ratios.map((ratio, i) => {
        const props = columns.itemProps(ratio)
        return (
          <div
            // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length fixture
            key={i}
            data-testid={`item-${i}`}
            className={props.className}
            style={props.style}
          />
        )
      })}
    </div>
  )
}

/** jsdom reports every element as 0×0, so the container states its own width. */
function setup({ enabled = true, ratios = [] } = {}) {
  Object.defineProperty(HTMLElement.prototype, 'getBoundingClientRect', {
    configurable: true,
    value: () => ({ width: WIDTH, height: 0, top: 0, left: 0, right: 0, bottom: 0 }),
  })
  render(<Harness enabled={enabled} ratios={ratios} />)
}

const spanOf = (index) => {
  const value = screen.getByTestId(`item-${index}`).style.gridRowEnd
  return Number(value.replace('span ', ''))
}

describe('useMasonryColumns', () => {
  it('gives a portrait the tracks its real height needs', () => {
    // 2:3 portrait in a 196px column is 294px tall, plus the 8px margin that
    // draws the gap between one image and the next.
    setup({ ratios: [2 / 3] })
    expect(spanOf(0)).toBe(Math.ceil(COLUMN / (2 / 3) + GAP))
  })

  it('makes a taller image span more than a shorter one, in proportion', () => {
    setup({ ratios: [1, 0.5] })
    const square = spanOf(0) - GAP
    const tall = spanOf(1) - GAP
    // Half the ratio is twice the height, within the 1px the ceiling costs.
    expect(Math.abs(tall - square * 2)).toBeLessThanOrEqual(1)
  })

  it('measures a wide image against the full width, since it takes both columns', () => {
    setup({ ratios: [WIDE_RATIO] })
    expect(screen.getByTestId('item-0')).toHaveClass('is-wide')
    expect(spanOf(0)).toBe(Math.ceil(WIDTH / WIDE_RATIO + GAP))
  })

  it('leaves an image just under the threshold in one column', () => {
    setup({ ratios: [WIDE_RATIO - 0.01] })
    expect(screen.getByTestId('item-0')).not.toHaveClass('is-wide')
  })

  it('always spans at least one track, however wide the image', () => {
    setup({ ratios: [100] })
    expect(spanOf(0)).toBeGreaterThanOrEqual(1)
  })

  it('stays out of the way when the wide layout is in use', () => {
    setup({ enabled: false, ratios: [2 / 3] })
    expect(screen.getByTestId('item-0').style.gridRowEnd).toBe('')
    expect(screen.getByTestId('item-0')).not.toHaveClass('is-wide')
  })
})
