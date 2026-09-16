import { useEffect, useState } from 'react'
import { traitsToKeys } from '../utils/characterTraits'

/**
 * The character editor's fields.
 *
 * Split out of `CharacterPage`, which held the record, the toolbar modes, the
 * lightbox, the accent picker and this form in one function. The rule is
 * unchanged: the fields are seeded from the record whenever it changes, so the
 * editor shows exactly what the identity block beside it shows, and the four
 * pool facets are keyed the same way.
 */
export function useCharacterEdit(char) {
  const [editMode, setEditMode] = useState(false)
  const [editName, setEditName] = useState('')
  const [editSeries, setEditSeries] = useState('')
  const [editRank, setEditRank] = useState('')
  const [editTraits, setEditTraits] = useState([])

  useEffect(() => {
    if (!char) return
    setEditName(char.name)
    setEditSeries(char.series || '')
    setEditRank(char.rank || '')
    setEditTraits(traitsToKeys(char.is_female, char.is_male, char.pools))
  }, [char])

  const toggleEditTrait = (key) =>
    setEditTraits((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]))

  return {
    editMode,
    setEditMode,
    editName,
    setEditName,
    editSeries,
    setEditSeries,
    editRank,
    setEditRank,
    editTraits,
    setEditTraits,
    toggleEditTrait,
  }
}
