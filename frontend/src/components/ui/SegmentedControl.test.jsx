/**
 * The Name / Series switch.
 *
 * Real radios in a fieldset give arrow-key navigation and group announcement
 * for free, and the `short` label exists so the control can shrink on a phone
 * without the word disappearing for anyone listening. That last distinction —
 * the drawn text changing while the spoken name does not — is exactly the sort
 * of thing a tidy-up flattens, so it is the one pinned hardest here.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import SegmentedControl from './SegmentedControl'

const OPTIONS = [
  { value: 'name', label: 'Name' },
  { value: 'series', label: 'Series', short: 'S' },
]

function setup(overrides = {}) {
  const onChange = vi.fn()
  render(
    <SegmentedControl
      name="search-by"
      label="Search by"
      value="name"
      onChange={onChange}
      options={OPTIONS}
      {...overrides}
    />,
  )
  return onChange
}

describe('SegmentedControl', () => {
  it('is a group of radios named by its label', () => {
    setup()

    expect(screen.getByRole('group', { name: 'Search by' })).toBeInTheDocument()
    expect(screen.getAllByRole('radio')).toHaveLength(2)
  })

  it('marks the current option as checked', () => {
    setup()

    expect(screen.getByRole('radio', { name: 'Name' })).toBeChecked()
    expect(screen.getByRole('radio', { name: 'Series' })).not.toBeChecked()
  })

  it('reports the value the person chose', async () => {
    const onChange = setup()

    await userEvent.click(screen.getByRole('radio', { name: 'Series' }))

    expect(onChange).toHaveBeenCalledWith('series')
  })

  it('keeps the full word in the accessible name when the drawn label is shortened', () => {
    setup()

    // Drawn as "S", announced as "Series".
    expect(screen.getByRole('radio', { name: 'Series' })).toBeInTheDocument()
    expect(screen.queryByRole('radio', { name: 'S' })).not.toBeInTheDocument()
  })
})
