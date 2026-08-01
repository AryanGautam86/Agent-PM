/**
 * One project's tasks: its own progress bar, its own add-task form, its own
 * list.
 *
 * A component per project rather than a loop in the parent, because each needs
 * its own queries and mutations — React hooks cannot be called in a loop.
 */

import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { Spinner } from '@/components/ui/Spinner'
import { ErrorState } from '@/components/ui/States'
import { ActionItemRow } from '@/features/action_items/ActionItemRow'
import {
  useActionItems,
  useCreateActionItem,
  useDeleteActionItem,
  useUpdateActionItem,
} from '@/features/action_items/api'
import { fromDateInput } from '@/features/action_items/dates'
import { summarise } from '@/features/action_items/progress'
import { useArchiveEngagement } from '@/features/engagements/api'
import type { Engagement } from '@/types/api'

export function ProjectSection({
  engagement,
  defaultOpen,
}: {
  engagement: Engagement
  defaultOpen: boolean
}) {
  const [open, setOpen] = useState(defaultOpen)
  const [adding, setAdding] = useState(false)
  const [title, setTitle] = useState('')
  const [owner, setOwner] = useState('')
  const [due, setDue] = useState('')

  const items = useActionItems(engagement.id)
  const create = useCreateActionItem(engagement.id)
  const update = useUpdateActionItem(engagement.id)
  const remove = useDeleteActionItem(engagement.id)
  const archive = useArchiveEngagement()

  const progress = summarise(items.data ?? [])
  const tone =
    progress.overdue > 0 ? 'danger' : progress.percent === 100 ? 'success' : 'accent'

  function handleAdd(event: FormEvent) {
    event.preventDefault()
    if (!title.trim()) return
    create.mutate(
      {
        title: title.trim(),
        owner_label: owner.trim() || undefined,
        due_at: fromDateInput(due) ?? undefined,
      },
      {
        onSuccess: () => {
          setTitle('')
          setOwner('')
          setDue('')
        },
      },
    )
  }

  return (
    <section className="project-card project-card-removable">
      <button
        type="button"
        className="project-head"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
      >
        <span className="project-caret" aria-hidden="true">
          {open ? '▾' : '▸'}
        </span>
        <span className="project-title">
          <strong>{engagement.name}</strong>
          {engagement.client_name && (
            <span className="muted"> · {engagement.client_name}</span>
          )}
        </span>
        <span className="project-meta project-meta-inset">
          {items.isLoading ? (
            <span className="muted">loading…</span>
          ) : progress.total === 0 ? (
            <span className="muted">no tasks</span>
          ) : (
            <>
              <span className="muted">
                {progress.done}/{progress.total - progress.cancelled} done
              </span>
              {progress.overdue > 0 && (
                <span className="badge badge-danger">{progress.overdue} overdue</span>
              )}
              <span className="project-percent">{progress.percent}%</span>
            </>
          )}
        </span>
      </button>

      <button
        type="button"
        className="icon-btn project-remove"
        title={`Remove project "${engagement.name}"`}
        aria-label={`Remove project ${engagement.name}`}
        disabled={archive.isPending}
        onClick={() => {
          if (
            window.confirm(
              `Remove "${engagement.name}"?\n\n` +
                'It disappears from your projects. Its standups, RAID items ' +
                'and approvals are kept, so the record of who approved what ' +
                'survives.',
            )
          ) {
            archive.mutate(engagement.id)
          }
        }}
      >
        ✕
      </button>

      <div className={`progress-track progress-${tone} project-bar`}>
        <div className="progress-fill" style={{ width: `${progress.percent}%` }} />
      </div>

      {open && (
        <div className="project-body">
          <div className="project-actions">
            <Button
              variant={adding ? 'ghost' : 'primary'}
              size="sm"
              onClick={() => setAdding((value) => !value)}
            >
              {adding ? 'Cancel' : '+ Add task'}
            </Button>
          </div>

          {adding && (
            <form className="inline-form project-add-form" onSubmit={handleAdd}>
              <input
                type="text"
                placeholder="What needs to happen?"
                autoFocus
                value={title}
                onChange={(event) => setTitle(event.target.value)}
                disabled={create.isPending}
                required
              />
              <input
                type="text"
                placeholder="Owner"
                value={owner}
                onChange={(event) => setOwner(event.target.value)}
                disabled={create.isPending}
              />
              <input
                type="date"
                aria-label={`Due date for new task in ${engagement.name}`}
                value={due}
                onChange={(event) => setDue(event.target.value)}
                disabled={create.isPending}
              />
              <Button type="submit" variant="primary" loading={create.isPending}>
                Add
              </Button>
            </form>
          )}

          {create.isError && <ErrorState error={create.error} />}
          {update.isError && <ErrorState error={update.error} />}
          {remove.isError && <ErrorState error={remove.error} />}
          {archive.isError && <ErrorState error={archive.error} />}

          {items.isLoading ? (
            <Spinner label="Loading tasks" />
          ) : items.error ? (
            <ErrorState error={items.error} onRetry={() => void items.refetch()} />
          ) : (items.data?.length ?? 0) === 0 ? (
            <p className="muted">
              No tasks yet. Use <strong>+ Add task</strong>, or they arrive
              automatically from meeting outcomes.
            </p>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Task</th>
                    <th>Owner</th>
                    <th>Due</th>
                    <th>Status</th>
                    <th>Progress</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {items.data?.map((item) => (
                    <ActionItemRow
                      key={item.id}
                      item={item}
                      busy={update.isPending || remove.isPending}
                      onPatch={(patch) => update.mutate({ itemId: item.id, patch })}
                      onDelete={() => remove.mutate(item.id)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
