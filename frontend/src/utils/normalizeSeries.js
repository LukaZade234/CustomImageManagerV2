/**
 * Case/space-insensitive comparison, matching the backend's folded name key.
 * Used wherever a typed name or series is checked against the catalog's.
 */
export function normalizeSeries(value) {
  return (value || '').normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase()
}
