import { useCallback, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'

import { Button, Card, ConfirmDialog, EmptyState } from '../../components/ui'
import { useMe } from '../../queries/me'
import {
  useDeleteModerationHistory,
  useModerationHistory,
  useModerationUserCharacters,
  useModerationUserImages,
  useModerationUsers,
  useRestoreModerationImage,
  useSetModerationRole,
  useWarnModerationUser,
} from '../../queries/moderation'
import { useStore } from '../../store/useStore'
import ContributorFinder from './ContributorFinder'
import ModerationHistory from './ModerationHistory'
import UserProfile from './UserProfile'
import UserWork from './UserWork'

/**
 * The moderation surface, in two states rather than a master–detail split.
 *
 * Open, it is a **finder**: a prominent search and a row of facets over the
 * contributor list, all in memory. Pick someone and the page becomes their
 * **Info / Images** tabs — Info is the profile and the moderation history,
 * Images is their work with its own character and added/removed filters. The
 * master pane used to sit permanently beside a detail column; a name you are
 * looking for is a search, not a list to scroll.
 *
 * It still pulls rather than pushes: nothing is counted pending, and it is
 * opened deliberately. See docs/MODERATION.md.
 *
 * State lives in the URL (`?user=<ref>&tab=images&state=removed&char=Rem&sort=rank&page=2`)
 * so it is linkable and the back button steps through what was actually looked
 * at. The discipline is CustomsPage's: a default value is the *absence* of the
 * parameter, a filter change resets `page` with `replace`, and a selection
 * pushes.
 */

const SORTS = {
  count: { order: 'desc' },
  rank: { order: 'asc' },
  name: { order: 'asc' },
  recent: { order: 'desc' },
}
const DEFAULT_SORT = 'count'

const TABS = [
  { value: 'info', label: 'Info' },
  { value: 'images', label: 'Images' },
]

export default function ModerationPage() {
  const [params, setParams] = useSearchParams()
  const { pathname } = useLocation()
  const user = params.get('user') ?? ''
  const tab = params.get('tab') === 'images' ? 'images' : 'info'
  const view = params.get('view') === 'characters' ? 'characters' : 'images'
  const state = params.get('state') === 'removed' ? 'removed' : 'active'
  const character = params.get('char') ?? ''
  const requestedSort = params.get('sort')
  const sort = requestedSort && SORTS[requestedSort] ? requestedSort : DEFAULT_SORT
  const order = params.get('order') ?? SORTS[sort].order
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
  // who you are looking at resets everything that belonged to the last person.
  const selectUser = (userRef) =>
    update({
      user: userRef,
      tab: '',
      view: '',
      state: '',
      char: '',
      sort: '',
      order: '',
      page: '',
    })
  const searchAnother = () =>
    update({ user: '', tab: '', view: '', state: '', char: '', sort: '', order: '', page: '' })
  // A tab is a place within one contributor, so it is a real link (the same tab
  // bar the profile uses) that replaces rather than pushes: Back leaves the
  // contributor rather than walking their tabs. `info` is the default, so it is
  // the absence of the parameter.
  const tabHref = (value) => {
    const next = new URLSearchParams(params)
    if (value === 'info') next.delete('tab')
    else next.set('tab', value)
    const query = next.toString()
    return `${pathname}${query ? `?${query}` : ''}`
  }
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
        order: SORTS[value].order === 'desc' ? '' : SORTS[value].order,
        page: '',
      },
      { replace: true },
    )
  const setPage = (value) => update({ page: value <= 1 ? '' : String(value) })
  // Clicking a character drills into this contributor's images on it, rather
  // than leaving for the public character page.
  const showCharacterImages = (name) => update({ view: '', char: name, page: '' })

  const usersQuery = useModerationUsers()
  const onImagesTab = tab === 'images'
  const imagesQuery = useModerationUserImages({
    ref: user,
    state,
    character,
    page,
    enabled: onImagesTab,
  })
  const charactersQuery = useModerationUserCharacters({
    ref: user,
    state,
    character,
    sort,
    order,
    page,
    enabled: onImagesTab,
  })
  const historyQuery = useModerationHistory(user)

  const { data: me } = useMe()
  const addToast = useStore((s) => s.addToast)
  const restoreImage = useRestoreModerationImage()
  const setRole = useSetModerationRole()
  const warnUser = useWarnModerationUser()
  const deleteHistory = useDeleteModerationHistory()
  const [historyToDelete, setHistoryToDelete] = useState(null)

  const handleRestore = (row) => {
    restoreImage.mutate(
      { character: row.character, url: row.url },
      {
        onSuccess: () => addToast('Image restored', 'success'),
        onError: (err) => addToast(err.message, 'error'),
      },
    )
  }
  const handleChangeRole = (role) => {
    setRole.mutate(
      { ref: user, role },
      {
        onSuccess: () =>
          addToast(
            role === 'moderator' ? 'Promoted to moderator' : 'Moderator role removed',
            'success',
          ),
        onError: (err) => addToast(err.message, 'error'),
      },
    )
  }
  // Resolves true only once it lands, so the dialog knows whether to close.
  const handleWarn = async (values) => {
    try {
      await warnUser.mutateAsync({ ref: user, ...values })
      addToast('Warning sent', 'success')
      return true
    } catch (err) {
      addToast(err.message, 'error')
      return false
    }
  }
  const handleDeleteHistory = () => {
    const target = historyToDelete
    setHistoryToDelete(null)
    if (!target) return
    deleteHistory.mutate(target.id, {
      onSuccess: () => addToast('Moderation record deleted', 'success'),
      onError: (err) => addToast(err.message, 'error'),
    })
  }
  const restoringUrl = restoreImage.isPending ? (restoreImage.variables?.url ?? null) : null

  const users = usersQuery.data?.items ?? []
  const selected = users.find((item) => item.ref === user) ?? null

  const pageBody = (
    <>
      <div className="moderation-head">
        <h1 className="page-title">Moderation</h1>
        {user && (
          <Link className="moderation-back" to={pathname}>
            ← Search another contributor
          </Link>
        )}
      </div>

      {!user ? (
        <>
          <p className="text-meta moderation-lead">
            Find a contributor to see who they are and what they have added or removed.
          </p>
          <ContributorFinder
            users={users}
            loading={usersQuery.isPending}
            error={usersQuery.isError ? usersQuery.error.message : null}
            onSelect={selectUser}
            onRetry={usersQuery.refetch}
          />
        </>
      ) : !selected ? (
        usersQuery.isPending ? (
          <p className="text-meta" role="status">
            Loading…
          </p>
        ) : (
          <EmptyState
            title="Contributor not found"
            description="They are no longer in the contributor list."
            action={<Button onClick={searchAnother}>Search contributors</Button>}
          />
        )
      ) : (
        <>
          <nav className="profile-tabs" aria-label="Contributor sections">
            {TABS.map((item) => {
              const active = tab === item.value
              return (
                <Link
                  key={item.value}
                  to={tabHref(item.value)}
                  replace
                  className={`profile-tab ${active ? 'profile-tab--active' : ''}`}
                  aria-current={active ? 'page' : undefined}
                >
                  {item.label}
                </Link>
              )
            })}
          </nav>

          {tab === 'info' ? (
            <div className="moderation-tabpanel">
              <UserProfile
                user={selected}
                canManageRoles={Boolean(me?.is_owner)}
                onChangeRole={handleChangeRole}
                onWarn={handleWarn}
              />
              <ModerationHistory
                items={historyQuery.data?.items}
                loading={historyQuery.isPending}
                error={historyQuery.isError ? historyQuery.error.message : null}
                onRetry={historyQuery.refetch}
                canDelete={Boolean(me?.is_owner)}
                onDelete={setHistoryToDelete}
              />
            </div>
          ) : (
            <div className="moderation-tabpanel">
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
                onShowCharacter={showCharacterImages}
                onRestore={handleRestore}
                restoringUrl={restoringUrl}
              />
            </div>
          )}
        </>
      )}

      {historyToDelete && (
        <ConfirmDialog
          title="Delete this moderation record?"
          body={`"${historyToDelete.title}" will be removed from ${selected?.handle ?? 'their'} moderation history, and the message it sent will be deleted from their inbox.`}
          confirmLabel="Delete record"
          variant="danger"
          onConfirm={handleDeleteHistory}
          onCancel={() => setHistoryToDelete(null)}
        />
      )}
    </>
  )

  return (
    <Card
      as="section"
      padding="md"
      className="moderation-page moderation-page--ledger moderation-detail--ledger"
    >
      {pageBody}
    </Card>
  )
}
