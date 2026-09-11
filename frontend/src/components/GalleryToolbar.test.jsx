/**
 * The gallery mode bar.
 *
 * This is a wide seam — twenty-odd callbacks handed down from CharacterPage —
 * and a mistyped prop name renders a button that simply does nothing when
 * clicked, with no error anywhere. So the test worth having is not that the
 * markup is right but that every button is wired to the callback it claims,
 * and that each mode shows only its own controls.
 */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { GalleryToolbar } from './GalleryToolbar'

const handlerNames = [
  'onEnterRemove',
  'onEnterDownload',
  'onEnterReorder',
  'onExitMode',
  'onCancelReorder',
  'onDoneReorder',
  'onSelectAll',
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
  it('browse mode offers the entry points and nothing else', async () => {
    const handlers = setup()
    await clickExpecting(/Remove or hide/i, handlers, 'onEnterRemove')

    expect(screen.queryByRole('button', { name: /Copy Command/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^Done$/i })).not.toBeInTheDocument()
  })

  it.each([
    ['Download', 'onEnterDownload'],
    ['Reorder', 'onEnterReorder'],
    ['Add Image', 'onAddImage'],
    ['Removed', 'onOpenRemovedDrawer'],
  ])('browse: %s calls %s', async (label, fired) => {
    await clickExpecting(new RegExp(`^${label}$`, 'i'), setup(), fired)
  })

  it('disables Add Image while an upload is in flight', () => {
    setup({ uploadBusy: true })
    expect(screen.getByRole('button', { name: /Add Image/i })).toBeDisabled()
  })

  it('ai mode copies the command and counts the selection', async () => {
    const handlers = setup({ mode: 'ai' })
    await clickExpecting(/Copy Command \(2\)/, handlers, 'onGenerateAiCommand')
  })

  it('ai mode counts every image when nothing is selected', () => {
    setup({ mode: 'ai', selectedUrls: [] })
    expect(screen.getByRole('button', { name: /Copy Command \(5\)/ })).toBeInTheDocument()
  })

  it('remove mode separates your images from other people’s', async () => {
    const handlers = setup({ mode: 'remove' })
    await clickExpecting(/Remove mine \(1\)/, handlers, 'onRemoveSelected')

    const fresh = setup({ mode: 'remove' })
    await clickExpecting(/Hide theirs \(1\)/, fresh, 'onHideSelected')
  })

  it('remove mode disables each action when its side of the selection is empty', () => {
    setup({ mode: 'remove', mineSelected: [], othersSelected: [] })
    expect(screen.getByRole('button', { name: /Remove mine/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /Hide theirs/i })).toBeDisabled()
  })

  it('download mode downloads the selection', async () => {
    await clickExpecting(/Download \(2\)/, setup({ mode: 'download' }), 'onDownloadSelected')
  })

  it('download mode disables the action with nothing selected', () => {
    setup({ mode: 'download', selectedUrls: [] })
    expect(screen.getByRole('button', { name: /Download \(0\)/ })).toBeDisabled()
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

  it.each(['ai', 'remove', 'download'])('%s mode exits through Cancel', async (mode) => {
    await clickExpecting(/^Cancel$/i, setup({ mode }), 'onExitMode')
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
