import { EmptyState } from '../../components/ui'

/**
 * Reported images — a placeholder, deliberately blank.
 *
 * Reports already exist and already act: two distinct reporters remove an image
 * (`DECISIONS.md` §1). What does not exist yet is a *queue* for a moderator to
 * read them in, and whether one should is still an open question (the roadmap's
 * "the reports question"). A tab is here so the shape of the staff area is
 * settled; the table behind it is not built until that question is answered.
 */
export default function ReportsPage() {
  return (
    <>
      <h2 className="section-heading">Reports</h2>
      <p className="text-meta moderation-lead">
        Images the community has reported. Two distinct reporters already remove an image; this is
        where the reports themselves will be readable.
      </p>
      <EmptyState
        title="Not built yet"
        description="The reports list is still an open design question — see the roadmap. Nothing is missing from the report flow itself."
      />
    </>
  )
}
