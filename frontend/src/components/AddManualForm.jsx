import ExistingCharacterCard from './ExistingCharacterCard'
import { PoolFilterChips } from './PoolFilterChips'
import SeriesSuggestInput from './SeriesSuggestInput'
import SignInPrompt from './SignInPrompt'
import { Button, Field, Input } from './ui'

/**
 * The right-hand panel of the Add workbench: the hand-typed add form.
 *
 * Everything it needs arrives in one `form` object rather than fifteen props.
 * The state is not its own — a Mudae lookup in the panel beside it pre-fills
 * these same fields — so the page owns it and this stays presentational.
 */
export default function AddManualForm({ form }) {
  const {
    name,
    series,
    rank,
    imageFile,
    status,
    loading,
    poolFilter,
    nameSuggestionItems,
    seriesSuggestionValues,
    duplicateName,
    seriesMismatch,
    nameMatch,
    catalogImage,
    catalogImageSrc,
    canAddImages = true,
    onNameChange,
    onSeriesChange,
    onRankChange,
    onImageChange,
    onPickName,
    onTogglePool,
    onSubmit,
  } = form

  return (
    <div className="edit-form-container add-char-panel">
      <h3 className="section-heading">Manual add</h3>
      <form onSubmit={onSubmit} className="add-char-form field-stack">
        <Field label="Character Name" htmlFor="addCharName" className="full-width">
          <SeriesSuggestInput
            id="addCharName"
            className="ui-input"
            placeholder="e.g. Saber"
            value={name}
            onChange={(e) => onNameChange(e.target.value)}
            suggestions={nameSuggestionItems}
            onPick={onPickName}
            ariaLabel="Character name suggestions"
            ariaDescribedBy={status?.type === 'error' ? 'addCharStatus' : undefined}
            required
          />
        </Field>
        {duplicateName && <ExistingCharacterCard character={nameMatch} />}
        <Field label="Series" htmlFor="addCharSeries" className="full-width">
          <SeriesSuggestInput
            id="addCharSeries"
            className="ui-input"
            placeholder="Series Name"
            value={series}
            onChange={(e) => onSeriesChange(e.target.value)}
            suggestions={seriesSuggestionValues}
            ariaLabel="Series suggestions"
            ariaInvalid={seriesMismatch}
          />
          {seriesMismatch && (
            <p className="form-error" role="alert">
              Series doesn&apos;t match — &quot;{nameMatch.name}&quot; is in &quot;
              {nameMatch.series}&quot;.
            </p>
          )}
        </Field>
        <PoolFilterChips value={poolFilter} onToggle={onTogglePool} />
        <Field label="Rank (Optional)" htmlFor="addCharRank" className="full-width">
          <Input
            id="addCharRank"
            type="number"
            placeholder="Leave blank to skip"
            value={rank}
            onChange={(e) => onRankChange(e.target.value)}
          />
        </Field>
        <Field label="Main Photo (Optional)" htmlFor="addCharImage" className="full-width">
          {catalogImage ? (
            <div className="add-char-image-preview">
              <img src={catalogImageSrc} alt="" className="add-char-image-preview__img" />
              <p className="mudae-preview__hint">
                The library&apos;s main image is used automatically and cannot be replaced.
              </p>
            </div>
          ) : !canAddImages ? (
            <div className="add-char-photo-gate">
              <p className="mudae-preview__hint">
                Uploading a photo needs a linked Discord account. A character from the library can
                still be added without one.
              </p>
              <SignInPrompt note="to upload a photo" />
            </div>
          ) : (
            <label className="file-upload-box" htmlFor="addCharImage">
              <svg
                aria-hidden="true"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="file-upload-icon"
              >
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <span id="addCharImageLabel" className="file-upload-hint">
                {imageFile ? imageFile.name : 'Click to select image (can be added later)'}
              </span>
              <input
                id="addCharImage"
                type="file"
                accept="image/*"
                className="sr-only"
                onChange={(e) => onImageChange(e.target.files?.[0] || null)}
              />
            </label>
          )}
        </Field>
        <div className="edit-actions add-char-actions">
          <Button variant="primary" type="submit" disabled={loading}>
            {loading ? 'Adding...' : 'Add Character'}
          </Button>
        </div>
        {status?.type === 'error' && (
          <div id="addCharStatus" className="form-error" role="alert">
            {status.message}
          </div>
        )}
      </form>
    </div>
  )
}
