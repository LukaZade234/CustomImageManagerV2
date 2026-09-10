import { getImageUrl } from '../api'
import { Button, Field, IconButton, Input } from './ui'

/**
 * The portrait, the character's details, and the form that edits them.
 *
 * The edit form's state stays in CharacterPage rather than moving here: saving
 * renames the character, which navigates and rewrites the stored custom-image
 * data, and the in-progress name is also what the `$ai` command uses when a
 * rename is being typed. Passing it down as one `edit` object keeps that seam
 * honest without spreading ten more props across the call site.
 */
export function CharacterHeader({
  char,
  mainImage,
  mainInputRef,
  loading,
  dragOver,
  onDragOverChange,
  onMainImageChange,
  onMainImageDrop,
  isSaved,
  onToggleSave,
  onGetAiCommand,
  edit,
  mudae,
}) {
  const portrait = (
    <>
      <input
        ref={mainInputRef}
        type="file"
        accept="image/*"
        style={{ display: 'none' }}
        onChange={onMainImageChange}
      />
      {mainImage ? (
        <img src={getImageUrl(mainImage)} alt={char.name} className="char-main-image-full" />
      ) : (
        <div className="char-main-placeholder">No image</div>
      )}
    </>
  )

  return (
    <div className="character-top-section">
      <div className="char-info-section">
        {!edit.active ? (
          <div>
            <h3 className="display-title">{char.name}</h3>
            <p className="text-body">{char.series || '\u2014'}</p>
            <p className="text-meta">Rank: {char.rank || '\u2014'}</p>
            <div className="char-page-actions">
              <Button
                variant="secondary"
                onClick={edit.start}
                title="Edit name, series, rank, and main image"
              >
                <svg
                  aria-hidden="true"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
                Edit Character
              </Button>
              <Button variant="secondary" onClick={onGetAiCommand}>
                <svg
                  aria-hidden="true"
                  width="16"
                  height="16"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                Get $ai Command
              </Button>
            </div>
          </div>
        ) : (
          <div className="char-edit-form">
            <Field label="Name" htmlFor="editCharName">
              <Input
                id="editCharName"
                type="text"
                placeholder="Character Name"
                value={edit.name}
                onChange={(e) => edit.setName(e.target.value)}
              />
            </Field>
            <Field label="Series" htmlFor="editCharSeries">
              <Input
                id="editCharSeries"
                type="text"
                placeholder="Series Name"
                value={edit.series}
                onChange={(e) => edit.setSeries(e.target.value)}
                autoComplete="off"
              />
            </Field>
            <Field label="Rank" htmlFor="editCharRank">
              <Input
                id="editCharRank"
                type="number"
                placeholder="#"
                value={edit.rank}
                onChange={(e) => edit.setRank(e.target.value)}
              />
            </Field>
            <div className="edit-actions">
              <Button variant="primary" onClick={edit.save} disabled={loading}>
                Save Changes
              </Button>
              <Button variant="secondary" onClick={edit.cancel}>
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>
      <div className="char-image-section">
        {edit.active ? (
          /**
           * Only a control while the character is being edited. The two branches
           * are spelled out rather than made conditional on one element: a div
           * that is sometimes a button and sometimes inert is both a real
           * accessibility problem and unreadable. As a real <button> it also
           * gets Enter, Space and focus for free, where the div needed its own
           * keydown handler and only ever honoured Enter.
           */
          <button
            type="button"
            className={`image-wrapper edit-mode ${dragOver ? 'drag-over-main' : ''}`}
            onClick={() => mainInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              onDragOverChange(true)
            }}
            onDragLeave={() => onDragOverChange(false)}
            onDrop={onMainImageDrop}
          >
            {portrait}
            <div className="image-overlay">
              <span>Click or Drop to Change</span>
            </div>
          </button>
        ) : (
          <div className="image-wrapper">{portrait}</div>
        )}
        {mudae.configured && (
          <div className="char-mudae-actions">
            <Button
              variant="secondary"
              disabled={mudae.busy || loading}
              onClick={mudae.onRefreshMain}
              title="Run $im via Mudae and set the card image as main"
            >
              {mudae.busy ? 'Updating from Mudae…' : 'Update main from Mudae'}
            </Button>
          </div>
        )}
        <IconButton
          className={`save-button ${isSaved ? 'saved' : ''}`}
          onClick={onToggleSave}
          label={isSaved ? 'Remove from saved' : 'Save this character'}
          aria-pressed={isSaved}
        >
          <svg
            aria-hidden="true"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
          >
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
          </svg>
        </IconButton>
      </div>
    </div>
  )
}
