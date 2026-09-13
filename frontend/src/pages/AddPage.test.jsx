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
  mudaeLookupSeries: vi.fn(),
  mudaeSeriesExtract: vi.fn(),
  mudaeSeriesExtractApply: vi.fn(),
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

/** Open the empty series field and choose its connected suggestion. */
async function pickSeries(user, label) {
  await user.click(screen.getByLabelText('Series'))
  await user.click(await screen.findByRole('option', { name: label }))
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
    // The series is not filled in; it is offered once the field is opened.
    expect(screen.getByLabelText('Series')).toHaveValue('')
    await pickSeries(user, 'Fate/stay night')
    expect(screen.getByLabelText('Series')).toHaveValue('Fate/stay night')

    await user.clear(screen.getByLabelText('Series'))
    await user.type(screen.getByLabelText('Series'), 'Wrong Series')
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
    await pickSeries(user, 'Fate/stay night')
    // The rank follows once the name and series match.
    await waitFor(() => expect(screen.getByLabelText('Rank (Optional)')).toHaveValue(4))
    await waitFor(() =>
      expect(document.querySelector('.add-char-image-preview__img')).toHaveAttribute(
        'src',
        'https://mudae.net/uploads/8363458/x.png',
      ),
    )
    // The library portrait is authoritative: no upload option is offered.
    expect(document.querySelector('#addCharImage')).toBeNull()

    await user.click(screen.getByRole('button', { name: /Add Character/ }))
    await waitFor(() => expect(api.addCharacter).toHaveBeenCalled())
    const formData = api.addCharacter.mock.calls[0][0]
    expect(formData.get('name')).toBe('Saber')
    expect(formData.get('series')).toBe('Fate/stay night')
    expect(formData.get('image_url')).toBe('https://mudae.net/uploads/8363458/x.png')
  })

  it('offers an upload for a character the library does not know', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.type(screen.getByLabelText('Character Name'), 'Totally Unknown')
    await waitFor(() => expect(api.findCatalogCharacter).toHaveBeenCalled())
    expect(document.querySelector('#addCharImage')).not.toBeNull()
  })

  it('offers a card instead of adding a character that already exists', async () => {
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
    await pickSeries(user, 'Re:Zero')
    const card = await screen.findByRole('link', { name: /Rem/ })
    expect(card).toHaveAttribute('href', '/character/Rem')

    await user.click(screen.getByRole('button', { name: /Add Character/ }))
    expect(api.addCharacter).not.toHaveBeenCalled()
  })

  it('hides the existing card as soon as the text stops matching', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockImplementation((value) =>
      Promise.resolve(
        value === 'Rem'
          ? {
              found: true,
              character: {
                name: 'Rem',
                series: 'Re:Zero',
                rank: '3',
                image: '',
                in_library: true,
              },
            }
          : { found: false, character: null },
      ),
    )
    renderPage()

    const input = screen.getByLabelText('Character Name')
    await user.type(input, 'Rem')
    await pickSeries(user, 'Re:Zero')
    expect(await screen.findByRole('link', { name: /Rem/ })).toBeInTheDocument()

    await user.type(input, 'x')
    expect(screen.queryByRole('link', { name: /Rem/ })).toBeNull()
  })

  it('hides the existing card when the series does not match', async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: {
        name: 'Rem',
        series: 'Re:Zero',
        rank: '3',
        image: '',
        in_library: true,
      },
    })
    renderPage()

    await user.type(screen.getByLabelText('Character Name'), 'Rem')
    await pickSeries(user, 'Re:Zero')
    expect(await screen.findByRole('link', { name: /Rem/ })).toBeInTheDocument()

    const seriesInput = screen.getByLabelText('Series')
    await user.clear(seriesInput)
    await user.type(seriesInput, 'Wrong Series')
    expect(screen.queryByRole('link', { name: /Rem/ })).toBeNull()
  })

  it("offers a series' characters as the name suggestions", async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({ found: false, character: null })
    api.suggestCharacters.mockImplementation((q, _limit, seriesArg) => {
      if (!q && seriesArg === 'Re:Zero') {
        return Promise.resolve({
          items: [
            { name: 'Rem', series: 'Re:Zero', rank: '3', image: '' },
            { name: 'Emilia', series: 'Re:Zero', rank: '2', image: '' },
          ],
        })
      }
      return Promise.resolve({ items: [] })
    })
    renderPage()

    await user.type(screen.getByLabelText('Series'), 'Re:Zero')
    await user.click(screen.getByLabelText('Character Name'))

    await waitFor(() => {
      const texts = screen.getAllByRole('option').map((option) => option.textContent)
      expect(texts.some((text) => text.includes('Rem'))).toBe(true)
      expect(texts.some((text) => text.includes('Emilia'))).toBe(true)
    })
    expect(api.suggestCharacters).toHaveBeenCalledWith('', 8, 'Re:Zero')
  })

  it("offers the matched name's series as the only series suggestion", async () => {
    const user = userEvent.setup()
    api.findCatalogCharacter.mockResolvedValue({
      found: true,
      character: {
        name: 'Saber',
        series: 'Fate/stay night',
        rank: '4',
        image: '',
        in_library: true,
      },
    })
    renderPage()

    await user.type(screen.getByLabelText('Character Name'), 'Saber')
    // Not auto-filled; offered only once the field is opened.
    expect(screen.getByLabelText('Series')).toHaveValue('')
    await user.click(screen.getByLabelText('Series'))

    await waitFor(() => {
      const options = screen.getAllByRole('option')
      expect(options).toHaveLength(1)
      expect(options[0]).toHaveTextContent('Fate/stay night')
    })
  })

  it('fills the series only when a name suggestion is picked, not when typed', async () => {
    const user = userEvent.setup()
    api.suggestCharacters.mockResolvedValue({
      items: [{ name: 'Saber', series: 'Fate/stay night', rank: '4', image: '' }],
    })
    renderPage()

    const nameInput = screen.getByLabelText('Character Name')
    await user.type(nameInput, 'Sab')
    // Typing alone leaves the series empty.
    expect(screen.getByLabelText('Series')).toHaveValue('')

    await user.click(await screen.findByRole('option', { name: /Saber/ }))
    expect(screen.getByLabelText('Series')).toHaveValue('Fate/stay night')
  })

  it('shows the existing card in the lookup panel', async () => {
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

    await user.type(screen.getByLabelText('Character name'), 'Rem')
    await user.click(screen.getByRole('button', { name: 'Lookup' }))

    expect(await screen.findByRole('link', { name: /Rem/ })).toHaveAttribute(
      'href',
      '/character/Rem',
    )
    expect(api.mudaeLookupCharacter).not.toHaveBeenCalled()
  })

  it('fetches a series, previews new vs existing, then applies it', async () => {
    const user = userEvent.setup()
    api.mudaeStatus.mockResolvedValue({ configured: true })
    api.mudaeLookupSeries.mockResolvedValue({
      type: 'series',
      series_label: 'Lord of the Mysteries',
    })
    api.mudaeSeriesExtract.mockResolvedValue({
      series: 'Lord of the Mysteries',
      total: 3,
      new_count: 2,
      update_count: 1,
      unchanged_count: 0,
      items: [
        {
          name: 'Klein Moretti',
          rank: '4252',
          image_url: 'https://mudae.net/a.png',
          in_library: false,
          changes: ['create'],
        },
        {
          name: 'Trissy',
          rank: '10320',
          image_url: 'https://mudae.net/b.png',
          in_library: false,
          changes: ['create'],
        },
        {
          name: 'Audrey Hall',
          rank: '8123',
          image_url: 'https://mudae.net/c.png',
          in_library: true,
          changes: ['series', 'rank', 'image'],
        },
      ],
    })
    api.mudaeSeriesExtractApply.mockResolvedValue({
      success: true,
      message: 'Series "Lord of the Mysteries" — added 2, updated 1, unchanged 0',
      created: 2,
      updated: 1,
      unchanged: 0,
      rejected: [],
    })
    renderPage()

    await user.type(await screen.findByLabelText('Bulk-add series'), 'Lord of the Mysteries')
    await user.click(screen.getByRole('button', { name: 'Fetch series' }))

    expect(api.mudaeLookupSeries).toHaveBeenCalledWith('Lord of the Mysteries')
    expect(await screen.findByText('Not in the library (2)')).toBeInTheDocument()
    expect(screen.getByText('Already in the library (1)')).toBeInTheDocument()
    expect(screen.getByText('updates series, rank, image')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Apply — add 2, update 1' }))

    await waitFor(() => expect(api.mudaeSeriesExtractApply).toHaveBeenCalled())
    const [seriesArg, items] = api.mudaeSeriesExtractApply.mock.calls[0]
    expect(seriesArg).toBe('Lord of the Mysteries')
    expect(items).toHaveLength(3)
    expect(items[0]).toMatchObject({ name: 'Klein Moretti', rank: '4252' })
    expect(api.getCharacters).toHaveBeenCalled()
  })

  it('offers series candidates when the name is ambiguous', async () => {
    const user = userEvent.setup()
    api.mudaeStatus.mockResolvedValue({ configured: true })
    api.mudaeLookupSeries.mockResolvedValue({
      type: 'candidates',
      candidate_matches: [
        { name: 'Re:Zero', series: '', label: 'Re:Zero - 12' },
        { name: 'Re:Zero kara Hajimeru', series: '', label: 'Re:Zero kara Hajimeru - 30' },
      ],
    })
    renderPage()

    await user.type(await screen.findByLabelText('Bulk-add series'), 'Re:Zero')
    await user.click(screen.getByRole('button', { name: 'Fetch series' }))

    expect(await screen.findByText('Pick a series:')).toBeInTheDocument()
    expect(api.mudaeSeriesExtract).not.toHaveBeenCalled()
  })
})
