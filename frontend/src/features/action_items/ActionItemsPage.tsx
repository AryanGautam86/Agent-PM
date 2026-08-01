/**
 * Tasks across every project.
 *
 * A project here is an engagement — the app's unit of work — so this page
 * lists them all rather than only the one selected in the sidebar. Each gets
 * its own progress bar and its own add-task form, and a new project can be
 * created without leaving the page.
 */

import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Spinner } from '@/components/ui/Spinner'
import { EmptyState, ErrorState } from '@/components/ui/States'
import { ProjectSection } from '@/features/action_items/ProjectSection'
import { toSlug, useCreateEngagement } from '@/features/engagements/api'
import { useEngagements } from '@/hooks/useEngagements'

export function ActionItemsPage() {
  const engagements = useEngagements()
  const create = useCreateEngagement()

  const [adding, setAdding] = useState(false)
  const [name, setName] = useState('')
  const [client, setClient] = useState('')

  const slug = toSlug(name)

  function handleCreate(event: FormEvent) {
    event.preventDefault()
    if (!name.trim() || !slug) return
    create.mutate(
      { name: name.trim(), slug, client_name: client.trim() || undefined },
      {
        onSuccess: () => {
          setName('')
          setClient('')
          setAdding(false)
        },
      },
    )
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1>Tasks</h1>
          <p className="muted">
            Every project you belong to, with its own progress. Owners are
            nudged before a task is due and escalated once overdue.
          </p>
        </div>
        <Button variant="primary" onClick={() => setAdding((value) => !value)}>
          {adding ? 'Cancel' : '+ New project'}
        </Button>
      </header>

      {adding && (
        <Card title="New project">
          <form className="inline-form" onSubmit={handleCreate}>
            <input
              type="text"
              placeholder="Project name"
              autoFocus
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={create.isPending}
              required
            />
            <input
              type="text"
              placeholder="Client (optional)"
              value={client}
              onChange={(event) => setClient(event.target.value)}
              disabled={create.isPending}
            />
            <Button
              type="submit"
              variant="primary"
              loading={create.isPending}
              disabled={!slug}
            >
              Create
            </Button>
          </form>
          {slug && (
            <p className="muted auth-note">
              Identifier: <code>{slug}</code> · agent identity{' '}
              <code>agent-pm-{slug}</code>. You become its delivery lead.
            </p>
          )}
          {create.isError && <ErrorState error={create.error} />}
        </Card>
      )}

      {engagements.isLoading ? (
        <Spinner label="Loading your projects" />
      ) : engagements.error ? (
        <ErrorState
          error={engagements.error}
          onRetry={() => void engagements.refetch()}
        />
      ) : (engagements.data?.length ?? 0) === 0 ? (
        <EmptyState
          title="No projects yet"
          hint="Create one to start tracking tasks."
          action={
            <Button variant="primary" onClick={() => setAdding(true)}>
              + New project
            </Button>
          }
        />
      ) : (
        <div className="stack">
          {engagements.data?.map((engagement) => (
            <ProjectSection
              key={engagement.id}
              engagement={engagement}
              // Every project starts open. Collapsing all but the first hid
              // the "+ Add task" button on the others, which made it look as
              // though only one project could take tasks.
              defaultOpen
            />
          ))}
        </div>
      )}
    </div>
  )
}
