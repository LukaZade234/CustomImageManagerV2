/**
 * The portrait and the character's details.
 *
 * Two things here are easy to break and invisible when broken: the portrait is
 * only a control while the character is being edited, and the edit form's state
 * lives in CharacterPage rather than here, so every field is wired through a
 * prop. Both are pinned below.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ getImageUrl: (p) => p || '' }))

import { CharacterHeader } from './CharacterHeader'

const char = { name: 'Ayanami Rei', series: 'Evangelion', rank: 12 }

function setup(overrides = {}) {
  const edit = {
    active: false,
    name: 'Ayanami Rei',
    series: 'Evangelion',
    rank: '12',
    setName: vi.fn(),
    setSeries: vi.fn(),
    setRank: vi.fn(),
    start: vi.fn(),
    cancel: vi.fn(),
    save: vi.fn(),
    ...(overrides.edit || {}),
  }
  const mudae = {
    configured: false,
    busy: false,
    onRefreshMain: vi.fn(),
    ...(overrides.mudae || {}),
  }
  const props = {
    char,
    mainImage: 'main.png',
    mainInputRef: { current: null },
    loading: false,
    dragOver: false,
    onDragOverChange: vi.fn(),
    onMainImageChange: vi.fn(),
    onMainImageDrop: vi.fn(),
    isSaved: false,
    onToggleSave: vi.fn(),
    onGetAiCommand: vi.fn(),
    customCount: 3,
    ...overrides,
    edit,
    mudae,
  }
  render(<CharacterHeader {...props} />)
  return props
}

describe('CharacterHeader', () => {
  it('shows the character and its actions when not editing', async () => {
    const props = setup()
    expect(screen.getByRole('heading', { name: 'Ayanami Rei' })).toBeInTheDocument()
    expect(screen.getByText('Evangelion')).toBeInTheDocument()
    expect(screen.getByText(/Rank: 12/)).toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Edit Character/i }))
    expect(props.edit.start).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: /Copy \$ai command/i }))
    expect(props.onGetAiCommand).toHaveBeenCalledTimes(1)
  })

  it('falls back to an em dash for a missing series or rank', () => {
    setup({ char: { name: 'Nobody' } })
    expect(screen.getAllByText('—')).toHaveLength(1)
    expect(screen.getByText('Rank: —')).toBeInTheDocument()
  })

  it('the portrait is inert until the character is being edited', () => {
    setup()
    // The only button on the image side is Save; the portrait is not a control.
    expect(screen.queryByText(/Click or Drop to Change/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Save this character/i })).toBeInTheDocument()
  })

  it('the portrait becomes a real button in edit mode', async () => {
    const props = setup({ edit: { active: true } })
    // React owns mainInputRef.current, so the spy goes on the element itself.
    const fileInput = document.querySelector('input[type="file"]')
    const clicked = vi.fn()
    fileInput.click = clicked
    const portrait = screen.getByRole('button', { name: /Click or Drop to Change/i })

    await userEvent.click(portrait)
    expect(clicked).toHaveBeenCalledTimes(1)

    // A <button> gets keyboard activation without a keydown handler of its own.
    portrait.focus()
    await userEvent.keyboard('{Enter}')
    expect(clicked).toHaveBeenCalledTimes(2)
    await userEvent.keyboard(' ')
    expect(clicked).toHaveBeenCalledTimes(3)
    expect(props.onGetAiCommand).not.toHaveBeenCalled()
  })

  it('edits are controlled by the page, not held here', async () => {
    const props = setup({ edit: { active: true } })
    await userEvent.type(screen.getByLabelText('Name'), 'X')
    expect(props.edit.setName).toHaveBeenCalledWith('Ayanami ReiX')

    await userEvent.type(screen.getByLabelText('Series'), 'X')
    expect(props.edit.setSeries).toHaveBeenCalledWith('EvangelionX')

    await userEvent.click(screen.getByRole('button', { name: /Save Changes/i }))
    expect(props.edit.save).toHaveBeenCalledTimes(1)

    await userEvent.click(screen.getByRole('button', { name: /^Cancel$/i }))
    expect(props.edit.cancel).toHaveBeenCalledTimes(1)
  })

  it('blocks saving while the page is busy', () => {
    setup({ edit: { active: true }, loading: true })
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeDisabled()
  })

  it('hides the Mudae refresh when Mudae is not configured', () => {
    setup()
    expect(
      screen.queryByRole('button', { name: /Update main from Mudae/i }),
    ).not.toBeInTheDocument()
  })

  it('shows the Mudae refresh when configured', async () => {
    const props = setup({ mudae: { configured: true } })
    await userEvent.click(screen.getByRole('button', { name: /Update main from Mudae/i }))
    expect(props.mudae.onRefreshMain).toHaveBeenCalledTimes(1)
  })

  it('disables the Mudae refresh while it is running', () => {
    setup({ mudae: { configured: true, busy: true } })
    expect(screen.getByRole('button', { name: /Updating from Mudae/i })).toBeDisabled()
  })

  it('reflects whether the character is already saved', async () => {
    const props = setup({ isSaved: true })
    const save = screen.getByRole('button', { name: /Remove from saved/i })
    expect(save).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(save)
    expect(props.onToggleSave).toHaveBeenCalledTimes(1)
  })
})
