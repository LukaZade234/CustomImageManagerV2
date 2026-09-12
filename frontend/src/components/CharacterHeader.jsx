import { getImageUrl } from '../api'
import { Button, Field, Input } from './ui'

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
  customCount,
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
    /*
      A two-by-two grid: portrait and identity on the top row, and the buttons
      for each directly beneath them on the second. The buttons are cells rather
      than the tails of two independent columns, so Save lands level with Edit
      and $ai by construction instead of by auto-margins guessing which column
      is taller. A long name pushes the whole button row down together, which is
      the one thing that should move it.
    */
    <div className="character-top-section">
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
            aria-label="Change the main image"
            onClick={() => mainInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              onDragOverChange(true)
            }}
            onDragLeave={() => onDragOverChange(false)}
            onDrop={onMainImageDrop}
          >
            {portrait}
          </button>
        ) : (
          <div className="image-wrapper">{portrait}</div>
        )}
      </div>
      <div className="char-info-section">
        {!edit.active ? (
          <div>
            <h1 className="display-title">{char.name}</h1>
            <p className="text-body">{char.series || '\u2014'}</p>
            <p className="text-meta">Rank: {char.rank || '\u2014'}</p>
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
              {/* Replacing the portrait is an editing action, so it sits with
                  the other ones rather than under the picture, where it was a
                  third of the space above the gallery for every visitor. */}
              {mudae.configured && (
                <Button
                  variant="secondary"
                  disabled={mudae.busy || loading}
                  onClick={mudae.onRefreshMain}
                  title="Run $im via Mudae and set the card image as main"
                >
                  {mudae.busy ? 'Updating from Mudae…' : 'Update main from Mudae'}
                </Button>
              )}
            </div>
          </div>
        )}
      </div>
      {/* Under the picture rather than on top of it. As a floating disc it
          covered a corner of a portrait that is now small enough for that to
          matter — and it is an action, so it belongs with the actions. It
          takes the portrait's width and the action buttons' height, which is
          what closes the gap beside them. */}
      <Button
        className={`save-button ${isSaved ? 'saved' : ''}`}
        variant="secondary"
        onClick={onToggleSave}
        title={isSaved ? 'Remove from saved' : 'Save this character'}
        aria-pressed={isSaved}
      >
        <svg
          aria-hidden="true"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          /* Filled once saved, so the state does not rest on colour alone. */
          fill={isSaved ? 'currentColor' : 'none'}
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
        </svg>
        {isSaved ? 'Saved' : 'Save'}
      </Button>
      {!edit.active && (
        <div className="char-page-actions">
          <Button
            variant="ghost"
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
            {/* The noun is the page you are standing on. It goes when the row
                has no width for it, which is under 480px. */}
            Edit <span className="label-optional">Character</span>
          </Button>
          {/*
              The door to the command, and the only one — which is the point.
              It used to copy every image the moment it was clicked, so there
              was no way to mean "all of them except those three", and the
              place you could say that was a Select button down by the gallery
              whose name gave no hint that $ai lived under it.
  
              It opens the selection with everything already chosen instead.
              Copying the lot is one more click; taking a few out is visible
              rather than hidden behind a button named after something else.
            */}
          {/* The one solid button on the browse screen. Producing the $ai
                command is what the page is for, and nothing on it led. */}
          <Button
            variant="primary"
            onClick={onGetAiCommand}
            disabled={customCount === 0}
            title={
              customCount === 0
                ? 'Add a custom image first'
                : `Choose which of the ${customCount} images go in the command, then copy it`
            }
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
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            $ai command
          </Button>
        </div>
      )}
    </div>
  )
}
