import { Link } from 'react-router-dom'
import { useStore } from '../store/useStore'
import { getImageUrl } from '../api'

export default function SavedPage() {
  const savedCharacters = useStore((s) => s.savedCharacters)
  const characters = useStore((s) => s.characters)
  const removeSaved = useStore((s) => s.removeSaved)
  const addToast = useStore((s) => s.addToast)

  const getCharImage = (name) => {
    const c = characters.find((x) => x.name === name)
    return c ? getImageUrl(c.image) : ''
  }

  const handleUnsave = async (e, name) => {
    e.preventDefault()
    e.stopPropagation()
    try {
      await removeSaved(name)
      addToast('Removed from saved', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  return (
    <div id="savedPage" className="saved-page">
      <h2 className="page-title">Saved Characters</h2>
      <p className="page-subtitle">Your personal collection of bookmarked characters.</p>
      {savedCharacters.length === 0 ? (
        <p className="empty-saved">No saved characters yet.</p>
      ) : (
        <div className="saved-characters-grid">
          {savedCharacters.map((char) => (
            <Link key={char.name} to={`/character/${encodeURIComponent(char.name)}`} className="saved-character-card">
              <div className="saved-card-image-wrap">
                {getCharImage(char.name) ? (
                  <img src={getCharImage(char.name)} alt={char.name} />
                ) : (
                  <div className="no-image-placeholder">No Image</div>
                )}
                <button
                  type="button"
                  className="saved-card-unsave-btn"
                  onClick={(e) => handleUnsave(e, char.name)}
                  title="Unsave"
                  aria-label="Unsave character"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                  </svg>
                </button>
              </div>
              <h4>{char.name}</h4>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
