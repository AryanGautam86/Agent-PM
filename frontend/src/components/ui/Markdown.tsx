import { markdownToBlocks } from '@/lib/format'

/**
 * Renders agent-produced markdown as React nodes.
 *
 * No `dangerouslySetInnerHTML`: this text comes from a language model, and
 * escaping it by construction is worth more than supporting every markdown
 * feature. Inline `**bold**` and `` `code` `` are handled; anything else
 * renders as plain text.
 */
export function Markdown({ source }: { source: string }) {
  if (!source.trim()) {
    return <p className="muted">No content.</p>
  }

  const blocks = markdownToBlocks(source)
  const nodes: React.ReactNode[] = []
  let bullets: string[] = []

  const flushBullets = (key: string) => {
    if (bullets.length === 0) return
    nodes.push(
      <ul key={key}>
        {bullets.map((text, index) => (
          <li key={index}>{renderInline(text)}</li>
        ))}
      </ul>,
    )
    bullets = []
  }

  blocks.forEach((block, index) => {
    if (block.kind === 'bullet') {
      bullets.push(block.text)
      return
    }
    flushBullets(`ul-${index}`)
    if (block.kind === 'heading') {
      nodes.push(<h3 key={index}>{renderInline(block.text)}</h3>)
    } else {
      nodes.push(<p key={index}>{renderInline(block.text)}</p>)
    }
  })
  flushBullets('ul-final')

  return <div className="markdown">{nodes}</div>
}

const INLINE = /(\*\*[^*]+\*\*|`[^`]+`|_[^_]+_)/g

function renderInline(text: string): React.ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    if (part.startsWith('**') && part.endsWith('**')) {
      return <strong key={index}>{part.slice(2, -2)}</strong>
    }
    if (part.startsWith('`') && part.endsWith('`')) {
      return <code key={index}>{part.slice(1, -1)}</code>
    }
    if (part.startsWith('_') && part.endsWith('_') && part.length > 2) {
      return <em key={index}>{part.slice(1, -1)}</em>
    }
    return part
  })
}
