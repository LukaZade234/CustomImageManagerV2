import { screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { renderWithQueryClient } from '../test/renderWithQueryClient'
import RestrictionBanner from './RestrictionBanner'

/**
 * The notice a restricted account sees. It exists because a ban cannot hide the
 * site, so the person is told in-app instead — this pins that it appears only
 * when there is a restriction, and says the right kind.
 */

const renderBanner = (me) =>
  renderWithQueryClient(<RestrictionBanner />, { queries: [[['me'], me]] })

describe('the restriction banner', () => {
  it('stays away when the account is fine', () => {
    renderBanner({ handle: 'Amber Otter', moderation_status: null })
    expect(screen.queryByRole('status')).not.toBeInTheDocument()
  })

  it('tells a banned account why nothing will save', () => {
    renderBanner({ moderation_status: 'banned', moderation_reason: 'spam' })
    const banner = screen.getByRole('status')
    expect(banner).toHaveTextContent(/banned/i)
    expect(banner).toHaveTextContent(/spam/)
  })

  it('gives a suspension its end date', () => {
    renderBanner({ moderation_status: 'suspended', moderation_until: '2026-02-01T00:00:00Z' })
    expect(screen.getByRole('status')).toHaveTextContent(/suspended until/i)
  })
})
