/**
 * This dialog only appears when an $ai command exceeds Discord's length limit,
 * which is rare enough that a broken import survived a merge to main: useRef was
 * dropped from its imports during the Phase 6 dialog rework, and nothing
 * rendered the component again until Biome's noUndeclaredVariables was turned
 * on. Rendering it once is enough to stop that recurring.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../store/useStore', () => ({ useStore: (select) => select({ addToast: vi.fn() }) }))

import AiCommandLimitDialog from './AiCommandLimitDialog'

describe('AiCommandLimitDialog', () => {
  it('renders without throwing', () => {
    render(
      <AiCommandLimitDialog
        charCount={2500}
        nonNitroParts={['$ai Rem https://cdn/a.png']}
        nitroParts={['$ai Rem https://cdn/a.png']}
        onClose={() => {}}
      />,
    )
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('shows both the regular and Nitro limits', () => {
    render(
      <AiCommandLimitDialog
        charCount={2500}
        nonNitroParts={['one', 'two']}
        nitroParts={['one']}
        onClose={() => {}}
      />,
    )
    expect(screen.getAllByRole('button', { name: /copy command/i }).length).toBeGreaterThan(0)
  })
})
