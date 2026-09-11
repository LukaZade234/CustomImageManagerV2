/**
 * The bar that appears along the bottom while a gallery mode is open.
 *
 * Two rules are pinned here, and both came out of using the thing.
 *
 * A verb is present only while the selection holds something it can act on —
 * which is what stops "Remove mine (0)" existing as a button you can reach,
 * read, and never use.
 *
 * And nothing that can hold focus is allowed to vanish under the caret. The
 * select-all control changes its own label rather than being replaced by a
 * clear button, and when the helpers do give way to the verbs, focus is moved
 * deliberately rather than being dropped to the top of a document whose gallery
 * is several screens long.
 */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { GallerySelectionBar } from './GallerySelectionBar'

const handlerNames = [
  'onSelectAll',
  'onSelectMine',
  'onClearSelection',
  'onGenerateAiCommand',
  'onDownloadSelected',
  'onRemoveSelected',
  'onHideSelected',
  'onExitMode',
  'onCancelReorder',
  'onDoneReorder',
]

function setup(overrides = {}) {
  cleanup()
  const handlers = Object.fromEntries(handlerNames.map((name) => [name, vi.fn()]))
  render(
    <GallerySelectionBar
      mode="select"
      selectedCount={2}
      totalCount={5}
      mineCount={1}
      mineSelectedCount={1}
      othersSelectedCount={1}
      {...handlers}
      {...overrides}
    />,
  )
  return handlers
}

async function clickExpecting(label, handlers, fired) {
  await userEvent.click(screen.getByRole('button', { name: label }))
  expect(handlers[fired]).toHaveBeenCalledTimes(1)
  for (const [name, fn] of Object.entries(handlers)) {
    if (name !== fired) expect(fn, `${name} should not have fired`).not.toHaveBeenCalled()
  }
}

const empty = { selectedCount: 0, mineSelectedCount: 0, othersSelectedCount: 0 }

describe('GallerySelectionBar', () => {
  it('names itself, so it can be found without hunting for it', () => {
    setup()
    expect(screen.getByRole('region', { name: /selection actions/i })).toBeInTheDocument()
  })

  it('says how much is selected out of how much there is', () => {
    // Asserted on the region rather than the text node: the number sits in its
    // own <strong>, so the paragraph's text is split across elements.
    setup({ selectedCount: 3, totalCount: 24 })
    expect(screen.getByRole('region')).toHaveTextContent('3 of 24 selected')
  })

  it('offers only the helpers until something is selected', () => {
    setup(empty)

    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Select all (5)',
      'Select mine (1)',
      '', // the Done cross, which is labelled rather than captioned
    ])
    expect(screen.getByRole('button', { name: /^Done$/i })).toBeInTheDocument()
  })

  it.each([
    [/Copy \$ai command/i, 'onGenerateAiCommand'],
    [/^Download$/i, 'onDownloadSelected'],
    [/^Remove \(1\)$/i, 'onRemoveSelected'],
    [/^Hide \(1\)$/i, 'onHideSelected'],
    [/^Done$/i, 'onExitMode'],
  ])('%s calls %s', async (label, fired) => {
    await clickExpecting(label, setup(), fired)
  })

  it('omits Remove when none of the selection is yours', () => {
    setup({ mineSelectedCount: 0 })
    expect(screen.queryByRole('button', { name: /^Remove/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Hide \(1\)$/i })).toBeInTheDocument()
  })

  it('omits Hide when the selection is all yours', () => {
    setup({ othersSelectedCount: 0 })
    expect(screen.queryByRole('button', { name: /^Hide \(/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Remove \(1\)$/i })).toBeInTheDocument()
  })

  it('counts only the verbs that act on part of the selection', () => {
    // Copy and Download take everything selected, and the bar has just said how
    // many that is. Remove and Hide take a share of it, which is the number you
    // cannot read anywhere else.
    setup({ selectedCount: 4, mineSelectedCount: 3, othersSelectedCount: 1 })
    expect(screen.getByRole('button', { name: 'Copy $ai command' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Remove (3)' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Hide (1)' })).toBeInTheDocument()
  })

  it('keeps one control for select-all and clear rather than swapping them', async () => {
    const none = setup(empty)
    await clickExpecting(/^Select all \(5\)$/i, none, 'onSelectAll')

    const some = setup()
    expect(screen.queryByRole('button', { name: /^Select all/i })).not.toBeInTheDocument()
    await clickExpecting(/^Clear$/i, some, 'onClearSelection')
  })

  it('offers Select mine as a way in, and drops it once you have a selection', () => {
    setup(empty)
    expect(screen.getByRole('button', { name: /^Select mine \(1\)$/i })).toBeInTheDocument()

    setup()
    expect(screen.queryByRole('button', { name: /Select mine/i })).not.toBeInTheDocument()
  })

  it('hides Select mine from someone who has added nothing here', () => {
    setup({ ...empty, mineCount: 0 })
    expect(screen.queryByRole('button', { name: /Select mine/i })).not.toBeInTheDocument()
  })

  it('takes the keyboard with it when it opens', () => {
    setup(empty)
    expect(document.activeElement).toBe(screen.getByRole('button', { name: /^Select all/i }))
  })

  it('reorder mode carries its own controls and no verbs', async () => {
    const handlers = setup({ mode: 'reorder', ...empty })
    expect(screen.getByRole('region', { name: /reorder actions/i })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /\$ai command/i })).not.toBeInTheDocument()

    // "Cancel" elsewhere means "leave without doing anything". The reorder
    // equivalent writes to the server, so it must not borrow that word.
    expect(screen.queryByRole('button', { name: /^Cancel$/i })).not.toBeInTheDocument()
    await clickExpecting(/^Discard changes$/i, handlers, 'onCancelReorder')

    await clickExpecting(/^Done$/i, setup({ mode: 'reorder', ...empty }), 'onDoneReorder')
  })

  it('says what to do while reordering, and what is being moved', () => {
    setup({ mode: 'reorder', ...empty })
    expect(screen.getByText(/Drag an image, or use the arrow keys/i)).toBeInTheDocument()

    setup({ mode: 'reorder', selectedCount: 3 })
    expect(screen.getByText(/Moving 3 together/i)).toBeInTheDocument()
  })
})
