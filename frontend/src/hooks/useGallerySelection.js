import { useCallback, useReducer } from 'react'

/**
 * The gallery's mode, selection and discard confirmation — one state machine.
 *
 * These were three separate `useState` values with a pile of hand-written
 * "turn the others off" lines, and most of the combinations they could be in
 * were nonsense. As one reducer every transition is a named event, so entering
 * a mode cannot leave the previous one's selection or a stale confirmation
 * behind, and a new mode cannot forget to reset them.
 */

const INITIAL = { mode: 'browse', selectedUrls: [], confirmDiscardOrder: false }

function reducer(state, action) {
  switch (action.type) {
    case 'browse':
      return INITIAL
    case 'select':
      return { mode: 'select', selectedUrls: action.urls, confirmDiscardOrder: false }
    case 'reorder':
      return { mode: 'reorder', selectedUrls: [], confirmDiscardOrder: false }
    case 'toggle':
      return {
        ...state,
        selectedUrls: state.selectedUrls.includes(action.url)
          ? state.selectedUrls.filter((url) => url !== action.url)
          : [...state.selectedUrls, action.url],
      }
    case 'selection':
      return { ...state, selectedUrls: action.urls }
    case 'askDiscard':
      return { ...state, confirmDiscardOrder: true }
    case 'cancelDiscard':
      return { ...state, confirmDiscardOrder: false }
    default:
      return state
  }
}

export function useGallerySelection() {
  const [state, dispatch] = useReducer(reducer, INITIAL)

  return {
    mode: state.mode,
    selectMode: state.mode === 'select',
    reorderMode: state.mode === 'reorder',
    selectedUrls: state.selectedUrls,
    confirmDiscardOrder: state.confirmDiscardOrder,
    reset: useCallback(() => dispatch({ type: 'browse' }), []),
    enterSelect: useCallback((urls = []) => dispatch({ type: 'select', urls }), []),
    enterReorder: useCallback(() => dispatch({ type: 'reorder' }), []),
    toggleUrl: useCallback((url) => dispatch({ type: 'toggle', url }), []),
    setSelection: useCallback((urls) => dispatch({ type: 'selection', urls }), []),
    askDiscard: useCallback(() => dispatch({ type: 'askDiscard' }), []),
    cancelDiscard: useCallback(() => dispatch({ type: 'cancelDiscard' }), []),
  }
}
