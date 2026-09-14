/**
 * The gender Mudae prints beside a character's series. A character can be in
 * both pools, so both signs can show. Each glyph carries an aria-label rather
 * than being read out as "female sign".
 */
export function GenderMarks({ isFemale, isMale }) {
  if (!isFemale && !isMale) return null
  return (
    <span className="char-gender">
      {isFemale && (
        <span className="char-gender__mark" role="img" aria-label="Female" title="Female">
          {'\u2640'}
        </span>
      )}
      {isMale && (
        <span className="char-gender__mark" role="img" aria-label="Male" title="Male">
          {'\u2642'}
        </span>
      )}
    </span>
  )
}
