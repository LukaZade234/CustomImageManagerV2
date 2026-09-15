import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ getImageUrl: (p) => p || '', getPortraitUrl: (p) => p || '' }))

import AddManualForm from './AddManualForm'

const character = { name: 'Rem', series: 'Re:Zero', rank: '3', in_library: true }

function makeForm(overrides = {}) {
  return {
    name: '',
    series: '',
    rank: '',
    imageFile: null,
    status: null,
    loading: false,
    poolFilter: [],
    nameSuggestionItems: [],
    seriesSuggestionValues: [],
    duplicateName: false,
    seriesMismatch: false,
    nameMatch: null,
    catalogImage: '',
    catalogImageSrc: '',
    onNameChange: vi.fn(),
    onSeriesChange: vi.fn(),
    onRankChange: vi.fn(),
    onImageChange: vi.fn(),
    onPickName: vi.fn(),
    onTogglePool: vi.fn(),
    onSubmit: vi.fn(),
    ...overrides,
  }
}

function renderForm(form = makeForm()) {
  render(
    <MemoryRouter>
      <AddManualForm form={form} />
    </MemoryRouter>,
  )
  return form
}

describe('AddManualForm', () => {
  it('reports every field to the page', async () => {
    const form = renderForm()
    await userEvent.type(screen.getByLabelText('Character Name'), 'R')
    expect(form.onNameChange).toHaveBeenCalledWith('R')

    await userEvent.type(screen.getByLabelText('Series'), 'S')
    expect(form.onSeriesChange).toHaveBeenCalledWith('S')

    await userEvent.type(screen.getByLabelText('Rank (Optional)'), '3')
    expect(form.onRankChange).toHaveBeenCalledWith('3')
  })

  it('submits through the page handler', async () => {
    const user = userEvent.setup()
    // The field is required, and the component is controlled by the page, so the
    // name has to already be there for the native submit to fire.
    const form = renderForm(makeForm({ name: 'Rem' }))
    await user.click(screen.getByRole('button', { name: /Add Character/ }))
    expect(form.onSubmit).toHaveBeenCalledTimes(1)
  })

  it('toggles the pool facets', async () => {
    const user = userEvent.setup()
    const form = renderForm(makeForm({ poolFilter: ['waifu'] }))
    expect(screen.getByRole('button', { name: 'Waifu' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: 'Game' }))
    expect(form.onTogglePool).toHaveBeenCalledWith('game')
  })

  it('offers the duplicate card in place of the plain fields', () => {
    renderForm(makeForm({ name: 'Rem', duplicateName: true, nameMatch: character }))
    expect(screen.getByRole('link', { name: /Rem/ })).toHaveAttribute('href', '/character/Rem')
  })

  it('shows the catalog portrait and withholds the upload', () => {
    renderForm(
      makeForm({
        name: 'Saber',
        catalogImage: 'https://mudae.net/saber.png',
        catalogImageSrc: 'https://mudae.net/saber.png',
      }),
    )
    expect(document.querySelector('.add-char-image-preview__img')).toHaveAttribute(
      'src',
      'https://mudae.net/saber.png',
    )
    expect(document.querySelector('#addCharImage')).toBeNull()
  })

  it('offers the upload when the library has no portrait', async () => {
    renderForm()
    await userEvent.type(screen.getByLabelText('Character Name'), 'Nobody')
    expect(document.querySelector('#addCharImage')).not.toBeNull()
  })

  it('asks a cookie-only visitor to sign in rather than offering an upload', () => {
    renderForm(makeForm({ canAddImages: false }))
    expect(document.querySelector('#addCharImage')).toBeNull()
    expect(screen.getByRole('link', { name: /Sign in with Discord/i })).toBeInTheDocument()
  })

  it('blocks adding a brand-new character without an account', () => {
    renderForm(makeForm({ canAddNewCharacter: false }))
    expect(screen.getByRole('button', { name: /Add Character/ })).toBeDisabled()
    expect(
      screen.getByText(/Adding a new character needs a linked Discord account/i),
    ).toBeInTheDocument()
  })

  it('renders an error status as an alert', () => {
    renderForm(makeForm({ status: { type: 'error', message: 'Nope' } }))
    expect(screen.getByRole('alert')).toHaveTextContent('Nope')
  })
})
