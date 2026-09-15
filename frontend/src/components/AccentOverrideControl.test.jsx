import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import AccentOverrideControl from './AccentOverrideControl'

function accent(overrides = {}) {
  return {
    canEdit: true,
    manual: false,
    pickMode: false,
    busy: false,
    seed: '#ff88cc',
    onTogglePick: vi.fn(),
    onClear: vi.fn(),
    ...overrides,
  }
}

describe('AccentOverrideControl', () => {
  it('renders nothing for a non-staff viewer', () => {
    const { container } = render(<AccentOverrideControl accent={accent({ canEdit: false })} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows the measured state with no reset', () => {
    render(<AccentOverrideControl accent={accent()} />)
    expect(screen.getByText('Measured')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Reset/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Pick from image/i })).toBeInTheDocument()
  })

  it('offers a reset once the colour is manual, and calls it', async () => {
    const user = userEvent.setup()
    const props = accent({ manual: true })
    render(<AccentOverrideControl accent={props} />)
    expect(screen.getByText('Manual')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /Reset to measured/i }))
    expect(props.onClear).toHaveBeenCalledTimes(1)
  })

  it('arms the picker and explains what to click', async () => {
    const user = userEvent.setup()
    const props = accent({ pickMode: true })
    render(<AccentOverrideControl accent={props} />)
    expect(screen.getByRole('status')).toHaveTextContent(/Click a pixel/i)
    await user.click(screen.getByRole('button', { name: /Cancel pick/i }))
    expect(props.onTogglePick).toHaveBeenCalledTimes(1)
  })
})
