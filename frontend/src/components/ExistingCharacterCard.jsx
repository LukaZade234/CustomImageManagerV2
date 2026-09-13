import { Link } from 'react-router-dom'
import { getImageUrl } from '../api'

/**
 * A compact, clickable card for a character the library already has.
 *
 * Shown by the Add flow when a typed name resolves to an existing character, so
 * the visitor is sent to that character's page rather than adding a duplicate.
 * Mirrors the browse-customs card: portrait, name, series.
 */
export default function ExistingCharacterCard({ character }) {
  if (!character) return null
  return (
    <Link
      to={`/character/${encodeURIComponent(character.name)}`}
      className="existing-character-card"
    >
      <img
        src={getImageUrl(character.image)}
        alt=""
        className="existing-character-card__img"
        width="56"
        height="87"
        loading="lazy"
        decoding="async"
      />
      <span className="existing-character-card__info">
        <span className="existing-character-card__name">{character.name}</span>
        {character.series && (
          <span className="existing-character-card__series">{character.series}</span>
        )}
        <span className="existing-character-card__hint">
          Already in the library — open its page
        </span>
      </span>
    </Link>
  )
}
