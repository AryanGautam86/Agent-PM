import { describe, expect, it } from 'vitest'

import { markdownToBlocks, percent, titleCase } from '@/lib/format'

describe('markdownToBlocks', () => {
  it('classifies headings, bullets and paragraphs', () => {
    const blocks = markdownToBlocks(
      ['## Blockers', '- DEMO-105 is stuck', 'Two items shipped.'].join('\n'),
    )

    expect(blocks).toEqual([
      { kind: 'heading', text: 'Blockers' },
      { kind: 'bullet', text: 'DEMO-105 is stuck' },
      { kind: 'paragraph', text: 'Two items shipped.' },
    ])
  })

  it('drops blank lines', () => {
    expect(markdownToBlocks('a\n\n\nb')).toHaveLength(2)
  })
})

describe('percent', () => {
  it('renders a ratio, and an em dash when there is nothing to render', () => {
    expect(percent(0.925)).toBe('93%')
    expect(percent(null)).toBe('—')
  })
})

describe('titleCase', () => {
  it('humanises enum values from the API', () => {
    expect(titleCase('raid_gap_add')).toBe('Raid Gap Add')
  })
})
