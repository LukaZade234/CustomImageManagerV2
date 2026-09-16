/** A native <select>, kept native so arrow keys and Escape work for free. */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import Select from './Select'

describe('Select', () => {
  it('offers its options and reports a choice', async () => {
    const onChange = vi.fn()
    render(
      <Select aria-label="Sort" defaultValue="name" onChange={onChange}>
        <option value="name">Name</option>
        <option value="rank">Rank</option>
      </Select>,
    )

    await userEvent.selectOptions(screen.getByLabelText('Sort'), 'rank')

    expect(onChange).toHaveBeenCalled()
  })

  it('forwards its ref to the select', () => {
    const ref = createRef()
    render(
      <Select aria-label="Sort" ref={ref}>
        <option value="name">Name</option>
      </Select>,
    )

    expect(ref.current).toBe(screen.getByLabelText('Sort'))
  })
})
