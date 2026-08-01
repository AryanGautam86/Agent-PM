import { Badge, StatusBadge } from '@/components/ui/Badge'
import { Button } from '@/components/ui/Button'
import { fromDateInput, toDateInput } from '@/features/action_items/dates'
import { formatDate, relativeTime, titleCase } from '@/lib/format'
import type { ActionItem, ActionItemStatus } from '@/types/api'

const STATUSES: ActionItemStatus[] = ['open', 'in_progress', 'done', 'cancelled']

export function ActionItemRow({
  item,
  busy,
  readOnly = false,
  onPatch,
  onDelete,
}: {
  item: ActionItem
  busy: boolean
  /** Non-admins see the row but cannot change it. */
  readOnly?: boolean
  onPatch: (patch: Partial<ActionItem>) => void
  onDelete: () => void
}) {
  const locked = busy || readOnly
  return (
    <tr className={item.is_overdue ? 'row-danger' : undefined}>
      <td>
        {item.title}
        {item.source !== 'manual' && (
          <span className="muted"> · from {titleCase(item.source)}</span>
        )}
      </td>

      <td>{item.owner_label ?? '—'}</td>

      <td>
        <input
          type="date"
          className="date-cell"
          aria-label={`Due date for ${item.title}`}
          value={toDateInput(item.due_at)}
          disabled={locked}
          onChange={(event) => onPatch({ due_at: fromDateInput(event.target.value) })}
        />
        {item.due_at && (
          <div className="muted cell-note">
            {item.is_overdue ? (
              <Badge tone="danger">{relativeTime(item.due_at)}</Badge>
            ) : (
              relativeTime(item.due_at)
            )}
          </div>
        )}
      </td>

      <td>
        <select
          className="status-cell"
          aria-label={`Status of ${item.title}`}
          value={item.status}
          disabled={locked}
          onChange={(event) =>
            onPatch({ status: event.target.value as ActionItemStatus })
          }
        >
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {titleCase(value)}
            </option>
          ))}
        </select>
      </td>

      <td>
        <span className="muted cell-note">
          {item.status === 'done'
            ? `Completed ${formatDate(item.completed_at)}`
            : `Added ${formatDate(item.created_at)}${
                item.nudge_count > 0 ? ` · ${item.nudge_count} nudge(s)` : ''
              }`}
        </span>
      </td>

      <td>
        <div className="row-actions">
          {item.status !== 'done' && !readOnly ? (
            <Button
              size="sm"
              disabled={locked}
              onClick={() => onPatch({ status: 'done' })}
            >
              Done
            </Button>
          ) : item.status === 'done' ? (
            <StatusBadge value="done" />
          ) : null}
          {!readOnly && (
          <button
            type="button"
            className="icon-btn"
            title={`Remove "${item.title}"`}
            aria-label={`Remove ${item.title}`}
            disabled={locked}
            onClick={() => {
              // Deleting is irreversible and the row is small — a stray click
              // should not silently destroy someone's task.
              if (window.confirm(`Remove "${item.title}"?`)) onDelete()
            }}
          >
            ✕
          </button>
          )}
        </div>
      </td>
    </tr>
  )
}
