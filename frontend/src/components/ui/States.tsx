import type { ReactNode } from 'react'

import { ApiRequestError } from '@/lib/api-client'
import { Button } from '@/components/ui/Button'

export function EmptyState({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="state-block">
      <p className="state-title">{title}</p>
      {hint && <p className="muted">{hint}</p>}
      {action}
    </div>
  )
}

export function ErrorState({
  error,
  onRetry,
}: {
  error: unknown
  onRetry?: () => void
}) {
  const message =
    error instanceof ApiRequestError
      ? error.message
      : error instanceof Error
        ? error.message
        : 'Something went wrong.'

  const hint =
    error instanceof ApiRequestError && error.isAuthError
      ? 'Your session may have expired. Sign out and back in.'
      : undefined

  return (
    <div className="state-block state-error">
      <p className="state-title">{message}</p>
      {hint && <p className="muted">{hint}</p>}
      {onRetry && (
        <Button size="sm" onClick={onRetry}>
          Try again
        </Button>
      )}
    </div>
  )
}
