import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  mudaeStatus: vi.fn(),
  suggestCharacters: vi.fn(),
  suggestSeries: vi.fn(),
  findCatalogCharacter: vi.fn(),
  catalogAddCharacter: vi.fn(),
  mudaeLookupCharacter: vi.fn(),
  mudaeSeriesExtract: vi.fn(),
  mudaeSeriesExtractApply: vi.fn(),
}))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  getPortraitUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: api,
}))

import { renderWithQueryClient } from '../test/renderWithQueryClient'
import AddMudaePanel from './AddMudaePanel'

function renderPanel(props = {}) {
  const handlers = {
    onPrefill: vi.fn(),
    onError: vi.fn(),
    onClearError: vi.fn(),
    ...props,
  }
  renderWithQueryClient(
    <MemoryRouter>
      <AddMudaePanel name="" {...handlers} />
    </MemoryRouter>,
  )
  return handlers
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
  api.mudaeStatus.mockResolvedValue({ configured: false })
  api.suggestCharacters.mockResolvedValue({ items: [] })
  api.suggestSeries.mockResolvedValue({ items: [] })
  api.findCatalogCharacter.mockResolvedValue({ found: false, character: null })
})

describe('AddMudaePanel', () => {
  it('lifts a library match to the page so the form can fill in', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: {
        name: 'Rem',
        series: 'Re:Zero',
        rank: '3',
        image: 'https://mudae.net/x.png',
        in_library: false,
      },
    })
    const handlers = renderPanel()

    await user.type(screen.getByLabelText('Character name'), 'Rem')
    await user.click(screen.getByRole('button', { name: 'Lookup' }))

    await waitFor(() => expect(handlers.onPrefill).toHaveBeenCalled())
    expect(handlers.onPrefill.mock.calls[0][0]).toMatchObject({ name: 'Rem', series: 'Re:Zero' })
    expect(api.mudaeLookupCharacter).not.toHaveBeenCalled()
  })

  it('shows the existing card and never asks Mudae', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: { name: 'Rem', series: 'Re:Zero', rank: '3', in_library: true },
    })
    const handlers = renderPanel()

    await user.type(screen.getByLabelText('Character name'), 'Rem')
    await user.click(screen.getByRole('button', { name: 'Lookup' }))

    expect(await screen.findByRole('link', { name: /Rem/ })).toHaveAttribute(
      'href',
      '/character/Rem',
    )
    expect(api.mudaeLookupCharacter).not.toHaveBeenCalled()
    expect(handlers.onPrefill).not.toHaveBeenCalled()
  })

  it('reports a lookup failure to the page', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockRejectedValue(new Error('catalog down'))
    const handlers = renderPanel()

    await user.type(screen.getByLabelText('Character name'), 'Rem')
    await user.click(screen.getByRole('button', { name: 'Lookup' }))

    await waitFor(() => expect(handlers.onError).toHaveBeenCalledWith('catalog down'))
  })

  it('hides the bulk-series tool when Mudae is not configured', async () => {
    renderPanel()
    await waitFor(() => expect(api.mudaeStatus).toHaveBeenCalled())
    expect(screen.queryByLabelText('Bulk-add series')).toBeNull()
    expect(screen.getByText(/Bulk series import needs Mudae/)).toBeInTheDocument()
  })

  it('shows the bulk-series tool once Mudae is configured', async () => {
    api.mudaeStatus.mockResolvedValue({ configured: true })
    renderPanel()
    expect(await screen.findByLabelText('Bulk-add series')).toBeInTheDocument()
  })
})
