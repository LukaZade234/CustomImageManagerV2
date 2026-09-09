/** Join class names, dropping falsy entries. */
export function cx(...parts) {
  return parts.filter(Boolean).join(' ')
}
