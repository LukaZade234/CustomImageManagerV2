/**
 * The gallery mode bar.
 *
 * This is a wide seam — twenty-odd callbacks handed down from CharacterPage —
 * and a mistyped prop name renders a button that simply does nothing when
 * clicked, with no error anywhere. So the test worth having is not that the
 * markup is right but that every button is wired to the callback it claims,
 * and that each mode shows only its own controls.
 *
 * The other thing pinned here is the rule the redesign turns on: a verb is
 * present only while the selection contains something it can act on. Four of
 * the five old modes were the same interaction with the verb chosen up front,
 * which is how "Remove mine (0)" became a button you could reach, read, and
 * never use.
 */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { GalleryToolbar } from './GalleryToolbar'

const handlerNames = [
  'onEnterSelect',
  'onEnterReorder',
  'onExitMode',
  'onCancelReorder',
  'onDoneReorder',
  'onSelectAll',
  'onSelectMine',
  'onClearSelection',
  'onGenerateAiCommand',
  'onRemoveSelected',
  'onHideSelected',
  'onDownloadSelected',
  'onUnhideAll',
  'onToggleShowHidden',
  'onOpenRemovedDrawer',
  'onAddImage',
]

/** Renders fresh each time, so one test can exercise two modes in sequence. */
function setup(overrides = {}) {
  cleanup()
  const handlers = Object.fromEntries(handlerNames.map((name) => [name, vi.fn()]))
  render(
    <GalleryToolbar
      mode="browse"
      selectedUrls={['a', 'b']}
      totalCount={5}
      mineCount={1}
      mineSelected={['a']}
      othersSelected={['b']}
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
  it('browse offers three things to do, not seven', async () => {
    const handlers = setup()

    // Select, Reorder, Add image — plus Removed, which is the only route back
    // to something already taken away. The four verb-first entry points are
    // gone: they all lived behind a selection that did not exist yet.
    expect(screen.getAllByRole('button').map((b) => b.textContent)).toEqual([
      'Removed',
      'Select',
      'Reorder',
      'Add image',
    ])

    await clickExpecting(/^Select$/i, handlers, 'onEnterSelect')
    expect(screen.queryByRole('button', { name: /Remove or hide/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /\$ai command/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Download/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Done$/i })).not.toBeInTheDocument()
  })

  it.each([
    ['Reorder', 'onEnterReorder'],
    ['Add image', 'onAddImage'],
    ['Removed', 'onOpenRemovedDrawer'],
  ])('browse: %s calls %s', async (label, fired) => {
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

  it('select mode shows a verb only while the selection can carry it', async () => {
    const handlers = setup({ mode: 'select' })
    await clickExpecting(/Copy \$ai command \(2\)/i, handlers, 'onGenerateAiCommand')

    const download = setup({ mode: 'select' })
    await clickExpecting(/^Download \(2\)$/i, download, 'onDownloadSelected')

    const remove = setup({ mode: 'select' })
    await clickExpecting(/^Remove \(1\)$/i, remove, 'onRemoveSelected')

    const hide = setup({ mode: 'select' })
    await clickExpecting(/^Hide \(1\)$/i, hide, 'onHideSelected')
  })

  it('offers no verbs at all with an empty selection', () => {
    setup({ mode: 'select', selectedUrls: [], mineSelected: [], othersSelected: [] })

    for (const absent of [/Copy \$ai command/i, /^Download/i, /^Remove/i, /^Hide \(/i]) {
      expect(screen.queryByRole('button', { name: absent })).not.toBeInTheDocument()
    }
    expect(screen.getByText('0 of 5 selected')).toBeInTheDocument()
  })

  it('omits Remove entirely when none of the selection is yours', () => {
    setup({ mode: 'select', mineSelected: [] })
    expect(screen.queryByRole('button', { name: /^Remove/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Hide \(1\)$/i })).toBeInTheDocument()
  })

  it('omits Hide entirely when the selection is all yours', () => {
    setup({ mode: 'select', othersSelected: [] })
    expect(screen.queryByRole('button', { name: /^Hide \(/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Remove \(1\)$/i })).toBeInTheDocument()
  })

  it('keeps one control for select-all and clear rather than swapping them', async () => {
    // Swapping one button for another unmounts the element under the caret,
    // which is the focus loss the mode switches used to cause. One control that
    // changes its own label survives the state change.
    const empty = setup({ mode: 'select', selectedUrls: [] })
    await clickExpecting(/^Select all \(5\)$/i, empty, 'onSelectAll')

    const some = setup({ mode: 'select' })
    expect(screen.queryByRole('button', { name: /^Select all/i })).not.toBeInTheDocument()
    await clickExpecting(/^Clear selection$/i, some, 'onClearSelection')
  })

  it('reaches your own images in one click', async () => {
    await clickExpecting(/^Select mine \(1\)$/i, setup({ mode: 'select' }), 'onSelectMine')
  })

  it('hides Select mine from someone who has added nothing here', () => {
    setup({ mode: 'select', mineCount: 0 })
    expect(screen.queryByRole('button', { name: /Select mine/i })).not.toBeInTheDocument()
  })

  it('leaves select mode through Done, which changes nothing', async () => {
    await clickExpecting(/^Done$/i, setup({ mode: 'select' }), 'onExitMode')
  })

  it('reorder mode offers discard and done, not the generic exit', async () => {
    const handlers = setup({ mode: 'reorder' })
    await clickExpecting(/^Done$/i, handlers, 'onDoneReorder')

    // "Cancel" elsewhere means "leave without doing anything". The reorder
    // equivalent writes to the server, so it must not borrow that word.
    const fresh = setup({ mode: 'reorder' })
    expect(screen.queryByRole('button', { name: /^Cancel$/i })).not.toBeInTheDocument()
    await clickExpecting(/^Discard changes$/i, fresh, 'onCancelReorder')
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
