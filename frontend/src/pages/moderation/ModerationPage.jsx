import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Card } from '../../components/ui'
import { useModerationUserImages, useModerationUsers } from '../../queries/moderation'
import UserDetail from './UserDetail'
import UserList from './UserList'

/**
 * The moderation surface: a master list of contributors beside their work.
 *
 * It pulls rather than pushes. Nothing is counted as pending, nothing is
 * actionable here, and the acting verbs stay on the character page — this
 * answers "what has this person been doing?" and asks nothing of the operator in
 * return. See docs/MODERATION.md and DECISIONS.md §1.
 *
 * Selection and filters live in the URL (`?user=<ref>&state=removed&char=Rem&page=2`)
 * so the whole state is linkable and the back button steps through what was
 * actually looked at. The discipline is CustomsPage's: the default value is the
 * *absence* of the parameter, a filter change resets `page` with `replace`, and
 * a first selection pushes.
 */
export default function ModerationPage() {
  const [params, setParams] = useSearchParams()
  const user = params.get('user') ?? ''
  const state = params.get('state') === 'removed' ? 'removed' : 'active'
  const character = params.get('char') ?? ''
  const parsedPage = Number.parseInt(params.get('page') ?? '1', 10)
  const page = Number.isFinite(parsedPage) && parsedPage > 0 ? parsedPage : 1

  const update = useCallback(
    (patch, { replace = false } = {}) => {
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          for (const [key, value] of Object.entries(patch)) {
            if (value === null || value === undefined || value === '') next.delete(key)
            else next.set(key, String(value))
          }
          return next
        },
        { replace },
      )
    },
    [setParams],
  )

  // Picking a contributor is a place to return to, so it pushes; and changing
  // who you are looking at resets the filters that belonged to the last person.
  const selectUser = (userRef) => update({ user: userRef, state: '', char: '', page: '' })
  // A filter change is a correction, not a page you chose: it replaces, and it
  // sends the list back to its first page.
  const setState = (value) =>
    update({ state: value === 'active' ? '' : value, page: '' }, { replace: true })
  const setCharacter = (value) => update({ char: value, page: '' }, { replace: true })
  const setPage = (value) => update({ page: value <= 1 ? '' : String(value) })

  const usersQuery = useModerationUsers()
  const detailQuery = useModerationUserImages({ ref: user, state, character, page })

  const users = usersQuery.data?.items ?? []
  const selected = users.find((item) => item.ref === user) ?? null

  return (
    <Card as="section" padding="lg">
      <h1 className="page-title">Moderation</h1>
      <p className="text-meta moderation-lead">
        What each contributor has added and removed. Read-only — removal and restore live on the
        character page, where the image and its context are.
      </p>

      <div className="moderation">
        <UserList
          users={users}
          loading={usersQuery.isPending}
          error={usersQuery.isError ? usersQuery.error.message : null}
          selectedRef={user}
          onSelect={selectUser}
          onRetry={usersQuery.refetch}
        />
        <UserDetail
          userRef={user}
          user={selected}
          state={state}
          character={character}
          page={page}
          data={detailQuery.data}
          loading={detailQuery.isFetching}
          error={detailQuery.isError ? detailQuery.error.message : null}
          onState={setState}
          onCharacter={setCharacter}
          onPage={setPage}
          onRetry={detailQuery.refetch}
        />
      </div>
    </Card>
  )
}
