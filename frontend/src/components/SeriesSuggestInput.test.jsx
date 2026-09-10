/**
 * The series autocomplete.
 *
 * The suggestions were selectable only with `onMouseDown`, so a keyboard user
 * could see a list of options — correctly marked up with `role="option"` — and
 * had no way whatsoever to choose one. These tests exist so that cannot come
 * back, and they are written against the keyboard rather than the mouse for
 * that reason.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SeriesSuggestInput from './SeriesSuggestInput'

const SUGGESTIONS = ['Cyberpunk: Edgerunners', 'Evangelion', 'Frieren', 'Cowboy Bebop']

function setup(value = '') {
  const onChange = vi.fn()
  render(
    <SeriesSuggestInput id="series" value={value} onChange={onChange} suggestions={SUGGESTIONS} />,
  )
  return { onChange, input: screen.getByRole('combobox') }
}

describe('SeriesSuggestInput', () => {
  it('opens the list on focus and marks itself expanded', async () => {
    const { input } = setup()
    await userEvent.click(input)
    expect(screen.getByRole('listbox')).toBeInTheDocument()
    expect(input).toHaveAttribute('aria-expanded', 'true')
  })

  it('picks a suggestion with the arrow keys and Enter', async () => {
    const { onChange, input } = setup()
    await userEvent.click(input)
    await userEvent.keyboard('{ArrowDown}{ArrowDown}{Enter}')

    expect(onChange).toHaveBeenCalledWith({ target: { value: 'Evangelion' } })
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('points aria-activedescendant at the option the cursor is on', async () => {
    const { input } = setup()
    await userEvent.click(input)
    expect(input).not.toHaveAttribute('aria-activedescendant')

    await userEvent.keyboard('{ArrowDown}')
    const active = input.getAttribute('aria-activedescendant')
    expect(active).toBeTruthy()
    expect(document.getElementById(active)).toHaveTextContent('Cyberpunk: Edgerunners')
    expect(document.getElementById(active)).toHaveAttribute('aria-selected', 'true')
  })

  it('wraps around at both ends', async () => {
    const { input } = setup()
    await userEvent.click(input)
    // Up from nothing goes to the last option.
    await userEvent.keyboard('{ArrowUp}')
    let active = document.getElementById(input.getAttribute('aria-activedescendant'))
    expect(active).toHaveTextContent('Cowboy Bebop')

    await userEvent.keyboard('{ArrowDown}')
    active = document.getElementById(input.getAttribute('aria-activedescendant'))
    expect(active).toHaveTextContent('Cyberpunk: Edgerunners')
  })

  it('Escape closes the list without choosing anything', async () => {
    const { onChange, input } = setup()
    await userEvent.click(input)
    await userEvent.keyboard('{ArrowDown}{Escape}')

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    expect(onChange).not.toHaveBeenCalled()
  })

  it('leaves Enter alone when no option is selected, so forms still submit', async () => {
    const onSubmit = vi.fn((e) => e.preventDefault())
    const onChange = vi.fn()
    render(
      <form onSubmit={onSubmit}>
        <SeriesSuggestInput id="s" value="" onChange={onChange} suggestions={SUGGESTIONS} />
      </form>,
    )
    await userEvent.click(screen.getByRole('combobox'))
    await userEvent.keyboard('{Enter}')

    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('filters as you type', async () => {
    setup('cyber')
    await userEvent.click(screen.getByRole('combobox'))
    expect(screen.getAllByRole('option')).toHaveLength(1)
    expect(screen.getByRole('option')).toHaveTextContent('Cyberpunk: Edgerunners')
  })

  it('still picks with the mouse', async () => {
    const { onChange, input } = setup()
    await userEvent.click(input)
    await userEvent.click(screen.getByRole('option', { name: 'Frieren' }))
    expect(onChange).toHaveBeenCalledWith({ target: { value: 'Frieren' } })
  })
})
