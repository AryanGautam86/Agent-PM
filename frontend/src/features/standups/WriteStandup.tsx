/**
 * Write a standup by hand.
 *
 * The agent's version is a draft of record, not the only one — when somebody
 * ran the meeting and knows what was said, their words are better. Submitting
 * replaces the generated post for that day and kind, and the standup is then
 * marked as authored by a person rather than by a model.
 */

import { useState, type FormEvent } from 'react'

import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { ErrorState } from '@/components/ui/States'
import { useWriteStandup } from '@/features/standups/api'
import type { StandupKind } from '@/types/api'

function today(): string {
  return new Date().toISOString().slice(0, 10)
}

export function WriteStandup({ engagementId }: { engagementId: string | null }) {
  const write = useWriteStandup(engagementId)

  const [open, setOpen] = useState(false)
  const [kind, setKind] = useState<StandupKind>('morning')
  const [topic, setTopic] = useState('')
  const [summary, setSummary] = useState('')
  const [forDate, setForDate] = useState(today())
  const [saved, setSaved] = useState(false)

  function handleSubmit(event: FormEvent) {
    event.preventDefault()
    if (!topic.trim() || !summary.trim()) return
    write.mutate(
      {
        kind,
        topic: topic.trim(),
        summary_markdown: summary.trim(),
        for_date: forDate || undefined,
      },
      {
        onSuccess: () => {
          setTopic('')
          setSummary('')
          setSaved(true)
          setOpen(false)
        },
      },
    )
  }

  if (!open) {
    return (
      <Card
        title="Write a standup"
        subtitle="Add your own update instead of using the generated one."
        actions={
          <Button
            variant="primary"
            size="sm"
            onClick={() => {
              setOpen(true)
              setSaved(false)
            }}
          >
            + Write standup
          </Button>
        }
      >
        {saved ? (
          <p className="alert alert-info">
            Saved. It appears in the list below, marked as written by you.
          </p>
        ) : (
          <p className="muted">
            Useful when you ran the meeting and know what was actually said.
          </p>
        )}
      </Card>
    )
  }

  return (
    <Card
      title="Write a standup"
      actions={
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      }
    >
      <form className="auth-form" onSubmit={handleSubmit}>
        <div className="field-row">
          <label className="field">
            <span>Kind</span>
            <select
              value={kind}
              onChange={(event) => setKind(event.target.value as StandupKind)}
              disabled={write.isPending}
            >
              <option value="morning">Morning plan</option>
              <option value="eod">End of day</option>
            </select>
          </label>
          <label className="field">
            <span>Date</span>
            <input
              type="date"
              value={forDate}
              onChange={(event) => setForDate(event.target.value)}
              disabled={write.isPending}
            />
          </label>
        </div>

        <label htmlFor="standup-topic">Topic</label>
        <input
          id="standup-topic"
          type="text"
          maxLength={255}
          required
          autoFocus
          placeholder="Sprint 14 kickoff"
          value={topic}
          onChange={(event) => setTopic(event.target.value)}
          disabled={write.isPending}
        />

        <label htmlFor="standup-summary">Summary</label>
        <textarea
          id="standup-summary"
          required
          rows={7}
          placeholder={
            'What happened, what is next, what is blocked.\n\n' +
            '- Priya finishing the login screen\n' +
            '- Daniel blocked on vendor SSO'
          }
          value={summary}
          onChange={(event) => setSummary(event.target.value)}
          disabled={write.isPending}
        />
        <p className="muted auth-note">
          Markdown works: <code>-</code> for bullets, <code>**bold**</code>.
          Submitting replaces any generated post for this date and kind.
        </p>

        <Button
          type="submit"
          variant="primary"
          loading={write.isPending}
          disabled={!topic.trim() || !summary.trim()}
          full
        >
          Submit standup
        </Button>
      </form>
      {write.isError && <ErrorState error={write.error} />}
    </Card>
  )
}
