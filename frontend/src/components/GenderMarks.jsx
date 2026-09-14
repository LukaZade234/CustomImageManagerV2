/**
 * The gender Mudae prints beside a character's series, using Mudae's own emoji.
 * A character can be in both pools, so both marks can show. Each is a real
 * <img> with an alt, so it is announced as "Female"/"Male" rather than read as
 * a picture with no name.
 */
export function GenderMarks({ isFemale, isMale }) {
  if (!isFemale && !isMale) return null
  return (
    <span className="char-gender">
      {isFemale && (
        <img className="char-gender__mark" src="/emoji/female.webp" alt="Female" title="Female" />
      )}
      {isMale && (
        <img className="char-gender__mark" src="/emoji/male.webp" alt="Male" title="Male" />
      )}
    </span>
  )
}
