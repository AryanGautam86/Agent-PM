import { format, formatDistanceToNowStrict, isValid, parseISO } from 'date-fns'

export function formatDate(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = parseISO(value)
  return isValid(parsed) ? format(parsed, 'd MMM yyyy') : '—'
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = parseISO(value)
  return isValid(parsed) ? format(parsed, 'd MMM, HH:mm') : '—'
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return '—'
  const parsed = parseISO(value)
  if (!isValid(parsed)) return '—'
  const suffix = parsed.getTime() > Date.now() ? 'from now' : 'ago'
  return `${formatDistanceToNowStrict(parsed)} ${suffix}`
}

export function percent(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${Math.round(value * 100)}%`
}

export function titleCase(value: string): string {
  return value
    .replace(/[_-]/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

/**
 * Minimal markdown rendering: headings, bold, italics, inline code, links and
 * bullet lists. Deliberately not a full parser and deliberately not
 * `dangerouslySetInnerHTML` — agent output is model-generated text, and the
 * safest thing to do with it is render it as escaped React nodes.
 */
export function markdownToBlocks(
  markdown: string,
): Array<{ kind: 'heading' | 'paragraph' | 'bullet'; text: string }> {
  return markdown
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      if (line.startsWith('#')) {
        return { kind: 'heading' as const, text: line.replace(/^#+\s*/, '') }
      }
      if (line.startsWith('- ') || line.startsWith('* ')) {
        return { kind: 'bullet' as const, text: line.slice(2) }
      }
      return { kind: 'paragraph' as const, text: line }
    })
}
