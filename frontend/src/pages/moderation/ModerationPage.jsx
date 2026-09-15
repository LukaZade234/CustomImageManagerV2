import { useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

import { Card, EmptyState } from '../../components/ui'
import {
  useModerationUserCharacters,
  useModerationUserImages,
  useModerationUsers,
} from '../../queries/moderation'
import UserList from './UserList'
import UserProfile from './UserProfile'
import UserWork from './UserWork'

/**
 * The moderation surface: a master list of contributors beside the selected
 * one's profile and their work.
 *
 * It pulls rather than pushes. Nothing is counted as pending, and the action
 * buttons are inert — this answers "what has this person been doing?" and asks
 * nothing of the operator in return. See docs/MODERATION.md and DECISIONS.md §1.
 *
 * Selection and filters live in the URL (`?user=<ref>&view=characters&state=removed&char=Rem&sort=rank&page=2`)
 * so the whole state is linkable and the back button steps through what was
 * actually looked at. The discipline is CustomsPage's: the default value is the
 * *absence* of the parameter, a filter change resets `page` with `replace`, and
 * a first selection pushes.
 */

const DEFAULT_SORT = 'count'

/** The direction each sort reads best in, so choosing it does not need a second click. */
const SORT_ORDER = { count: 'desc', rank: 'asc', name: 'asc', recent: 'desc' }

export default function ModerationPage() {
  const [params, setParams] = useSearchParams()
  const user = params.get('user') ?? ''
  const view = params.get('view') === 'characters' ? 'characters' : 'images'
  const state = params.get('state') === 'removed' ? 'removed' : 'active'
  const character = params.get('char') ?? ''
  const requestedSort = params.get('sort')
  const sort = requestedSort && SORT_ORDER[requestedSort] ? requestedSort : DEFAULT_SORT
  const order = params.get('order') ?? SORT_ORDER[sort]
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
  const selectUser = (userRef) =>
    update({ user: userRef, view: '', state: '', char: '', sort: '', order: '', page: '' })
  // A filter change is a correction rather than a page you chose: it replaces,
  // and it sends the list back to its first page.
  const setView = (value) =>
    update({ view: value === 'images' ? '' : value, page: '' }, { replace: true })
  const setState = (value) =>
    update({ state: value === 'active' ? '' : value, page: '' }, { replace: true })
  const setCharacter = (value) => update({ char: value, page: '' }, { replace: true })
  const setSort = (value) =>
    update(
      {
        sort: value === DEFAULT_SORT ? '' : value,
        order: SORT_ORDER[value] === 'desc' ? '' : SORT_ORDER[value],
        page: '',
      },
      { replace: true },
    )
  const setPage = (value) => update({ page: value <= 1 ? '' : String(value) })

  const usersQuery = useModerationUsers()
  const imagesQuery = useModerationUserImages({ ref: user, state, character, page })
  const charactersQuery = useModerationUserCharacters({
    ref: user,
    state,
    character,
    sort,
    order,
    page,
  })

  const users = usersQuery.data?.items ?? []
  const selected = users.find((item) => item.ref === user) ?? null

  return (
    <Card as="section" padding="lg">
      <h1 className="page-title">Moderation</h1>
      <p className="text-meta moderation-lead">
        Who added and removed what. Read-only: every action is present but inert.
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

        <div className="moderation-main">
          {!user || !selected ? (
            <EmptyState
              title="Pick a contributor"
              description="Pick a contributor to see what they added and removed."
            />
          ) : (
            <>
              <UserProfile user={selected} />
              <UserWork
                view={view}
                state={state}
                character={character}
                sort={sort}
                page={page}
                images={{
                  data: imagesQuery.data,
                  loading: imagesQuery.isFetching,
                  error: imagesQuery.isError ? imagesQuery.error.message : null,
                  refetch: imagesQuery.refetch,
                }}
                characters={{
                  data: charactersQuery.data,
                  loading: charactersQuery.isFetching,
                  error: charactersQuery.isError ? charactersQuery.error.message : null,
                  refetch: charactersQuery.refetch,
                }}
                onView={setView}
                onState={setState}
                onCharacter={setCharacter}
                onSort={setSort}
                onPage={setPage}
              />
            </>
          )}
        </div>
      </div>
    </Card>
  )
}
