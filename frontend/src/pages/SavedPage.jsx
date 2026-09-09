import { Link } from 'react-router-dom'
import { getImageUrl } from '../api'
import { Card, EmptyState, IconButton } from '../components/ui'
import { useStore } from '../store/useStore'

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
    <Card as="section" padding="lg" className="saved-page">
      <h1 className="page-title">Saved Characters</h1>
      <p className="page-subtitle">Your personal collection of bookmarked characters.</p>
      {savedCharacters.length === 0 ? (
        <EmptyState
          title="No saved characters yet"
          description="Bookmark a character from its page and it will show up here for quick access."
        />
      ) : (
        <div className="saved-characters-grid">
          {savedCharacters.map((char) => (
            <Link
              key={char.name}
              to={`/character/${encodeURIComponent(char.name)}`}
              className="saved-character-card"
            >
              <div className="saved-card-image-wrap">
                {getCharImage(char.name) ? (
                  <img src={getCharImage(char.name)} alt={char.name} />
                ) : (
                  <div className="no-image-placeholder">No Image</div>
                )}
                <IconButton
                  size="sm"
                  className="saved-card-unsave-btn"
                  onClick={(e) => handleUnsave(e, char.name)}
                  label={`Remove ${char.name} from saved`}
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    aria-hidden="true"
                  >
                    <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
                  </svg>
                </IconButton>
              </div>
              <h4>{char.name}</h4>
            </Link>
          ))}
        </div>
      )}
    </Card>
  )
}
