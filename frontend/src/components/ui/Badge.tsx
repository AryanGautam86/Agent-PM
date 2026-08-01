import type { ReactNode } from 'react'

import { toneFor, type BadgeTone } from '@/components/ui/badge-tones'

interface BadgeProps {
  tone?: BadgeTone
  children: ReactNode
  title?: string
}

export function Badge({ tone = 'neutral', children, title }: BadgeProps) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  )
}

/** Badge whose tone is derived from the value itself. */
export function StatusBadge({ value }: { value: string | null | undefined }) {
  if (!value) return null
  return <Badge tone={toneFor(value)}>{value.replace(/_/g, ' ')}</Badge>
}
