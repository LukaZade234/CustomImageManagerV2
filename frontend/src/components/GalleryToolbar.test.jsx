/**
 * The row of controls beside the "Custom Images" heading.
 *
 * This is a wide seam — a dozen callbacks handed down from CharacterPage — and
 * a mistyped prop name renders a button that simply does nothing when clicked,
 * with no error anywhere. So the test worth having is not that the markup is
 * right but that every button is wired to the callback it claims.
 *
 * What is pinned beyond that is how little is here. There were seven controls,
 * four of which only chose which verb you would be allowed to use once you had
 * selected something. Those live in GallerySelectionBar now, after the images
 * are picked.
 */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { GalleryToolbar } from './GalleryToolbar'

const handlerNames = [
  'onEnterSelect',
  'onEnterReorder',
  'onUnhideAll',
  'onToggleShowHidden',
  'onOpenRemovedDrawer',
  'onAddImage',
]

/** Renders fresh each time, so one test can exercise two states in sequence. */
function setup(overrides = {}) {
  cleanup()
  const handlers = Object.fromEntries(handlerNames.map((name) => [name, vi.fn()]))
  render(
    <GalleryToolbar
      totalCount={5}
      hiddenCount={0}
      showHidden={false}
      uploadBusy={false}
      {...handlers}
      {...overrides}
    />,
  )
  return handlers
}

/** Click the button whose accessible name matches, then assert only `fired` ran. */
async function clickExpecting(label, handlers, fired) {
  await userEvent.click(screen.getByRole('button', { name: label }))
  expect(handlers[fired]).toHaveBeenCalledTimes(1)
  for (const [name, fn] of Object.entries(handlers)) {
    if (name !== fired) expect(fn, `${name} should not have fired`).not.toHaveBeenCalled()
  }
}

describe('GalleryToolbar', () => {
  it('offers three things to start, and the way back to what was removed', async () => {
    const handlers = setup()

    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Removed',
      'Select',
      'Reorder',
      'Add image',
    ])

    // The verbs are not up here any more: none of them can act until images are
    // chosen, and choosing happens in the bar along the bottom.
    for (const absent of [/Remove \(/i, /^Hide \(/i, /\$ai command/i, /^Download/i, /^Done$/i]) {
      expect(screen.queryByRole('button', { name: absent })).not.toBeInTheDocument()
    }
    await clickExpecting(/^Select$/i, handlers, 'onEnterSelect')
  })

  it.each([
    ['Reorder', 'onEnterReorder'],
    ['Add image', 'onAddImage'],
    ['Removed', 'onOpenRemovedDrawer'],
  ])('%s calls %s', async (label, fired) => {
    await clickExpecting(new RegExp(`^${label}$`, 'i'), setup(), fired)
  })

  it('disables Add image while an upload is in flight', () => {
    setup({ uploadBusy: true })
    expect(screen.getByRole('button', { name: /Add image/i })).toBeDisabled()
  })

  it('does not offer to select or reorder an empty gallery', () => {
    setup({ totalCount: 0 })
    expect(screen.getByRole('button', { name: /^Select$/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /^Reorder$/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Add image/i })).toBeEnabled()
  })

  it('does not offer to reorder a single image', () => {
    setup({ totalCount: 1 })
    expect(screen.getByRole('button', { name: /^Select$/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /^Reorder$/i })).toBeDisabled()
  })

  it('hidden images stay out of the way until there are some', () => {
    setup({ hiddenCount: 0 })
    expect(screen.queryByRole('button', { name: /hidden/i })).not.toBeInTheDocument()
  })

  it('reveals hidden images and offers to unhide them all', async () => {
    const handlers = setup({ hiddenCount: 3 })
    await clickExpecting(/Show 3 hidden/i, handlers, 'onToggleShowHidden')

    const shown = setup({ hiddenCount: 3, showHidden: true })
    expect(screen.getByRole('button', { name: /Hide them again/i })).toBeInTheDocument()
    await clickExpecting(/Unhide all \(3\)/i, shown, 'onUnhideAll')
  })
})
