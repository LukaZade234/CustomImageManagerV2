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

vi.mock('../api', () => ({ getImageUrl: (p) => p || '', getPortraitUrl: (p) => p || '' }))

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
    traits: [],
    toggleTrait: vi.fn(),
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
    pick: false,
    onPickPortrait: vi.fn(),
    accent: { canEdit: false },
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

    await userEvent.click(screen.getByRole('button', { name: /^\$ai command$/i }))
    expect(props.onGetAiCommand).toHaveBeenCalledTimes(1)
  })

  it('keeps the full label in the accessible name when the noun is hidden', () => {
    // "Character" is dropped by CSS under 480px, so it has to be a separate
    // node — and the space has to be its own node too, or the name computation
    // trims it and the button announces itself as "EditCharacter".
    setup()
    expect(screen.getByRole('button', { name: 'Edit Character' })).toBeInTheDocument()
    expect(document.querySelector('.label-optional')).toHaveTextContent('Character')
  })

  it('falls back to an em dash for a missing series or rank', () => {
    setup({ char: { name: 'Nobody' } })
    expect(screen.getAllByText('—')).toHaveLength(1)
    expect(screen.getByText('Rank: —')).toBeInTheDocument()
  })

  it('shows the gender sign beside the series and the pool list under it', () => {
    setup({
      char: {
        name: '9S',
        series: 'NieR: Automata',
        rank: 622,
        is_male: true,
        pools: 'Game & Animanga',
      },
    })
    expect(screen.getByRole('img', { name: 'Male' })).toBeInTheDocument()
    expect(screen.queryByRole('img', { name: 'Female' })).not.toBeInTheDocument()
    expect(screen.getByText('Game & Animanga')).toBeInTheDocument()
  })

  it('can show both genders', () => {
    setup({ char: { name: 'Truck-kun', is_female: true, is_male: true } })
    expect(screen.getByRole('img', { name: 'Female' })).toBeInTheDocument()
    expect(screen.getByRole('img', { name: 'Male' })).toBeInTheDocument()
  })

  it('shows neither when the card did not say', () => {
    setup()
    expect(screen.queryByRole('img', { name: /Female|Male/ })).not.toBeInTheDocument()
    expect(document.querySelector('.char-pools')).not.toBeInTheDocument()
  })

  it('the portrait is inert until the character is being edited', () => {
    setup()
    // The only button on the image side is Save; the portrait is not a control.
    expect(screen.queryByRole('button', { name: /Change the main image/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^Save$/ })).toBeInTheDocument()
  })

  it('turns the portrait into a picker while picking the accent', async () => {
    const props = setup({ pick: true, accent: { canEdit: true } })
    const button = screen.getByRole('button', { name: /Pick the accent colour from the portrait/i })
    await userEvent.click(button)
    expect(props.onPickPortrait).toHaveBeenCalledTimes(1)
  })

  it('the portrait becomes a real button in edit mode', async () => {
    const props = setup({ edit: { active: true } })
    // React owns mainInputRef.current, so the spy goes on the element itself.
    const fileInput = document.querySelector('input[type="file"]')
    const clicked = vi.fn()
    fileInput.click = clicked
    const portrait = screen.getByRole('button', { name: /Change the main image/i })

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

  it('edits the gender and roulette pools', async () => {
    const props = setup({ edit: { active: true, traits: ['waifu', 'game'] } })

    expect(screen.getByRole('button', { name: 'Waifu' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Game' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Husbando' })).toHaveAttribute(
      'aria-pressed',
      'false',
    )

    await userEvent.click(screen.getByRole('button', { name: 'Anime' }))
    expect(props.edit.toggleTrait).toHaveBeenCalledWith('anime')
  })

  it('hides the trait editor outside edit mode', () => {
    setup()
    expect(screen.queryByRole('button', { name: 'Waifu' })).not.toBeInTheDocument()
    expect(screen.queryByText(/Gender And Roulette Pools/i)).not.toBeInTheDocument()
  })

  it('blocks saving while the page is busy', () => {
    setup({ edit: { active: true }, loading: true })
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeDisabled()
  })

  it('hides the Mudae refresh when Mudae is not configured', () => {
    setup({ edit: { active: true } })
    expect(
      screen.queryByRole('button', { name: /Update main from Mudae/i }),
    ).not.toBeInTheDocument()
  })

  it('keeps the Mudae refresh out of the way until the character is being edited', () => {
    // Replacing the portrait is an editing action, and on a phone this button
    // was a third of the space above the gallery — offered to every visitor,
    // most of whom have no Mudae session behind it.
    setup({ mudae: { configured: true } })
    expect(
      screen.queryByRole('button', { name: /Update main from Mudae/i }),
    ).not.toBeInTheDocument()
  })

  it('shows the Mudae refresh while editing', async () => {
    const props = setup({ mudae: { configured: true }, edit: { active: true } })
    await userEvent.click(screen.getByRole('button', { name: /Update main from Mudae/i }))
    expect(props.mudae.onRefreshMain).toHaveBeenCalledTimes(1)
  })

  it('disables the Mudae refresh while it is running', () => {
    setup({ mudae: { configured: true, busy: true }, edit: { active: true } })
    expect(screen.getByRole('button', { name: /Updating from Mudae/i })).toBeDisabled()
  })

  it('reflects whether the character is already saved', async () => {
    const props = setup({ isSaved: true })
    // The visible word is the name, and the state rides on aria-pressed rather
    // than on a second, different label that speech control could not match.
    const save = screen.getByRole('button', { name: /^Saved$/ })
    expect(save).toHaveAttribute('aria-pressed', 'true')
    await userEvent.click(save)
    expect(props.onToggleSave).toHaveBeenCalledTimes(1)
  })
})

describe('the save button', () => {
  /**
   * It used to float over the portrait's top-right corner. That was tolerable
   * while the portrait was 280px tall and became a problem when it was not:
   * a 36px disc over a 108px-wide picture covers a lot of a face.
   */
  it('sits under the portrait rather than on top of it', () => {
    setup()
    const image = document.querySelector('.char-image-section')
    const save = screen.getByRole('button', { name: /^Save$/ })

    // Inside the portrait's own column, so a tall edit form beside it cannot
    // push it down — the bug that made it drop to the form's foot on edit.
    expect(save.parentElement).toBe(image)
    expect(image.querySelector('.char-image-section img')).toBeInTheDocument()
    expect(save.className).not.toMatch(/ui-btn--icon/)
  })

  it('keeps the page actions in the identity column', () => {
    setup()
    const info = document.querySelector('.char-info-section')
    const actions = document.querySelector('.char-page-actions')
    expect(actions.parentElement).toBe(info)
    expect(info.querySelector('.display-title')).toHaveTextContent('Ayanami Rei')
  })

  it('is the same kind of button as the actions it lines up with', () => {
    setup()
    const save = screen.getByRole('button', { name: /^Save$/ })
    const ai = screen.getByRole('button', { name: /\$ai command/i })
    // Same primitive and size, so their heights match without being told to.
    for (const cls of ['ui-btn', 'ui-btn--md']) {
      expect(save.className).toContain(cls)
      expect(ai.className).toContain(cls)
    }
  })
})
