/**
 * The Add flow's catalog integration.
 *
 * The catalog is the source of truth for names and series: suggestions come from
 * it, a known name offers its series, a mismatched series is refused, and a
 * lookup/add that the catalog can answer never reaches Discord.
 */
import { render, screen, waitFor } from '@testing-library/react'
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
  addCharacter: vi.fn(),
  getCharacters: vi.fn(),
}))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: api,
}))

import AddPage from './AddPage'

function renderPage() {
  return render(
    <MemoryRouter>
      <AddPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockReset()
  api.mudaeStatus.mockResolvedValue({ configured: false })
  api.suggestCharacters.mockResolvedValue({ items: [] })
  api.suggestSeries.mockResolvedValue({ items: [] })
  api.findCatalogCharacter.mockResolvedValue({ found: false, character: null })
  api.getCharacters.mockResolvedValue([])
})

describe('AddPage catalog integration', () => {
  it('offers the known series and refuses a mismatched one', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: { name: 'Saber', series: 'Fate/stay night', rank: '4', image: '' },
    })
    renderPage()

    await user.type(screen.getByLabelText('Character Name'), 'Saber')
    const seriesInput = await screen.findByDisplayValue('Fate/stay night')
    expect(seriesInput).toBe(screen.getByLabelText('Series'))

    await user.clear(seriesInput)
    await user.type(seriesInput, 'Wrong Series')
    expect(await screen.findByText(/Series doesn't match/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Add Character/ }))
    expect(api.addCharacter).not.toHaveBeenCalled()
  })

  it('looks a name up in the library without touching Mudae', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: { name: 'Rem', series: 'Re:Zero', rank: '3', image: 'https://mudae.net/x.png' },
    })
    renderPage()

    await user.type(screen.getByLabelText('Character name'), 'Rem')
    await user.click(screen.getByRole('button', { name: 'Lookup' }))

    await waitFor(() => expect(api.findCatalogCharacter).toHaveBeenCalledWith('Rem'))
    expect(api.mudaeLookupCharacter).not.toHaveBeenCalled()
    // The lookup pre-fills the manual form from the library's record.
    expect(screen.getByLabelText('Character Name')).toHaveValue('Rem')
    expect(screen.getByLabelText('Series')).toHaveValue('Re:Zero')
  })

  it('adds a catalog character without Mudae or ImgChest', async () => {
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
    api.catalogAddCharacter.mockResolvedValue({
      success: true,
      message: 'Added "Rem"',
      character: { name: 'Rem' },
    })
    renderPage()

    await user.type(screen.getByLabelText('Character name'), 'Rem')
    await user.click(screen.getByRole('button', { name: 'Add' }))

    await waitFor(() => expect(api.catalogAddCharacter).toHaveBeenCalledWith('Rem'))
    expect(api.mudaeLookupCharacter).not.toHaveBeenCalled()
  })

  it('falls back to Mudae only when the library does not know the name', async () => {
    const user = userEvent.setup()
    api.mudaeStatus.mockResolvedValue({ configured: true })
    api.mudaeLookupCharacter.mockResolvedValue({ type: 'candidates', candidate_matches: [] })
    renderPage()

    await user.type(screen.getByLabelText('Character name'), 'Unknown Person')
    await user.click(screen.getByRole('button', { name: 'Lookup' }))

    await waitFor(() => expect(api.findCatalogCharacter).toHaveBeenCalledWith('Unknown Person'))
    await waitFor(() =>
      expect(api.mudaeLookupCharacter).toHaveBeenCalledWith('Unknown Person', false),
    )
  })

  it('fills the portrait from the library and sends it with the form', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: {
        name: 'Saber',
        series: 'Fate/stay night',
        rank: '4',
        image: 'https://mudae.net/uploads/8363458/x.png',
        in_library: false,
      },
    })
    api.addCharacter.mockResolvedValue({ success: true })
    renderPage()

    await user.type(screen.getByLabelText('Character Name'), 'Saber')
    await screen.findByDisplayValue('Fate/stay night')
    await waitFor(() =>
      expect(document.querySelector('.add-char-image-preview__img')).toHaveAttribute(
        'src',
        'https://mudae.net/uploads/8363458/x.png',
      ),
    )

    await user.click(screen.getByRole('button', { name: /Add Character/ }))
    await waitFor(() => expect(api.addCharacter).toHaveBeenCalled())
    const formData = api.addCharacter.mock.calls[0][0]
    expect(formData.get('name')).toBe('Saber')
    expect(formData.get('series')).toBe('Fate/stay night')
    expect(formData.get('image_url')).toBe('https://mudae.net/uploads/8363458/x.png')
  })

  it('refuses to add a character that already exists', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: {
        name: 'Rem',
        series: 'Re:Zero',
        rank: '3',
        image: 'https://mudae.net/x.png',
        in_library: true,
      },
    })
    renderPage()

    await user.type(screen.getByLabelText('Character Name'), 'Rem')
    expect(await screen.findByText(/already exists/i)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Add Character/ }))
    expect(api.addCharacter).not.toHaveBeenCalled()
  })
})
